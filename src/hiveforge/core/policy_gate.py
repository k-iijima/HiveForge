"""Policy Gate - 中央集権的アクション判定

外部フィードバック対応: Action Classの判定ロジックを中央集権化し、散在を防ぐ。

全てのアクション（API/MCP/Queen→Worker割当）は Policy Gate を経由する。
これにより、判定ロジックが散在して事故するリスクを軽減する。
"""

from enum import StrEnum
from typing import Any

from hiveforge.core.models.action_class import ActionClass, TrustLevel


class PolicyDecision(StrEnum):
    """Policy Gateの判定結果"""

    ALLOW = "allow"  # 実行許可
    REQUIRE_APPROVAL = "require_approval"  # 承認必要
    DENY = "deny"  # 拒否


class PolicyGate:
    """Policy Gate（設定カスタマイズ対応）

    中央集権的にアクションの可否を判定する。
    設定によりデフォルト動作をカスタマイズ可能。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """初期化

        Args:
            config: カスタム設定
                - level3_irreversible_requires_approval: TrueならLevel 3 + IRREVERSIBLEも承認必須
                - tool_overrides: ツールごとのオーバーライド設定
        """
        self.config = config or {}

    def evaluate(
        self,
        actor: str,
        action_class: ActionClass,
        trust_level: TrustLevel,
        scope: str,
        scope_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """アクションの可否を判定

        Args:
            actor: 実行者（"user" | "beekeeper" | "queen:{colony_id}" | "worker:{worker_id}"）
            action_class: READ_ONLY | REVERSIBLE | IRREVERSIBLE
            trust_level: 0-3
            scope: "hive" | "colony" | "run" | "task"
            scope_id: スコープ対象のID（任意）
            context: 追加コンテキスト（ツール名、パラメータ等）

        Returns:
            PolicyDecision: ALLOW | REQUIRE_APPROVAL | DENY
        """
        # READ_ONLY は常に許可
        if action_class == ActionClass.READ_ONLY:
            return PolicyDecision.ALLOW

        # カスタム設定: Level 3 + IRREVERSIBLE でも承認必須
        level3_requires_approval = self.config.get("level3_irreversible_requires_approval", False)

        # Trust Level と Action Class のマトリクス判定
        if action_class == ActionClass.REVERSIBLE:
            # REVERSIBLE: Level 1以上は許可
            if trust_level.value >= TrustLevel.PROPOSE_CONFIRM.value:
                return PolicyDecision.ALLOW
            else:
                return PolicyDecision.REQUIRE_APPROVAL

        elif action_class == ActionClass.IRREVERSIBLE:
            # IRREVERSIBLE: Level 2以上は許可（設定次第）
            if trust_level.value >= TrustLevel.AUTO_NOTIFY.value:
                # Level 3 で設定が有効なら承認必須
                if trust_level == TrustLevel.FULL_DELEGATION and level3_requires_approval:
                    return PolicyDecision.REQUIRE_APPROVAL
                return PolicyDecision.ALLOW
            elif trust_level == TrustLevel.PROPOSE_CONFIRM:
                return PolicyDecision.REQUIRE_APPROVAL
            else:
                # Level 0 は IRREVERSIBLE を拒否
                return PolicyDecision.DENY

        # フォールバック: 承認必須
        return PolicyDecision.REQUIRE_APPROVAL


# デフォルトのPolicyGateインスタンス
_default_gate = PolicyGate()


def policy_gate(
    actor: str,
    action_class: ActionClass,
    trust_level: TrustLevel,
    scope: str,
    scope_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> PolicyDecision:
    """中央集権的なアクション判定（関数インターフェース）

    PolicyGateのデフォルトインスタンスを使用。
    カスタム設定が必要な場合はPolicyGateクラスを直接使用する。

    Args:
        actor: 実行者（"user" | "beekeeper" | "queen:{colony_id}" | "worker:{worker_id}"）
        action_class: READ_ONLY | REVERSIBLE | IRREVERSIBLE
        trust_level: 0-3
        scope: "hive" | "colony" | "run" | "task"
        scope_id: スコープ対象のID（任意）
        context: 追加コンテキスト（ツール名、パラメータ等）

    Returns:
        PolicyDecision: ALLOW | REQUIRE_APPROVAL | DENY
    """
    return _default_gate.evaluate(
        actor=actor,
        action_class=action_class,
        trust_level=trust_level,
        scope=scope,
        scope_id=scope_id,
        context=context,
    )
