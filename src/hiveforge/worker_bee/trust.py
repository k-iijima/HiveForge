"""ActionClass・TrustLevel

ツールの危険度分類と信頼レベルに基づく承認制御。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class ActionClass(str, Enum):
    """アクションの危険度分類

    Safe -> Careful -> Dangerous -> Critical の順に危険度が上がる
    """

    SAFE = "safe"
    """読み取り専用、副作用なし（ファイル読み取り、検索など）"""

    CAREFUL = "careful"
    """軽微な変更（ファイル作成、小規模編集）"""

    DANGEROUS = "dangerous"
    """重大な変更（ファイル削除、大規模編集、外部通信）"""

    CRITICAL = "critical"
    """回復困難な操作（システム変更、認証情報操作、不可逆操作）"""

    def __lt__(self, other: "ActionClass") -> bool:
        order = [ActionClass.SAFE, ActionClass.CAREFUL, ActionClass.DANGEROUS, ActionClass.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other: "ActionClass") -> bool:
        return self == other or self < other

    def __gt__(self, other: "ActionClass") -> bool:
        return not self <= other

    def __ge__(self, other: "ActionClass") -> bool:
        return not self < other


class TrustLevel(str, Enum):
    """エージェントの信頼レベル

    Untrusted -> Limited -> Standard -> Elevated -> Full の順に信頼度が上がる
    """

    UNTRUSTED = "untrusted"
    """未検証エージェント - SAFE操作のみ許可"""

    LIMITED = "limited"
    """制限付きエージェント - CAREFUL以下許可"""

    STANDARD = "standard"
    """標準エージェント - DANGEROUS以下許可（承認必要）"""

    ELEVATED = "elevated"
    """信頼済みエージェント - CRITICAL以外は自動承認"""

    FULL = "full"
    """完全信頼エージェント - 全操作自動承認"""

    def __lt__(self, other: "TrustLevel") -> bool:
        order = [
            TrustLevel.UNTRUSTED,
            TrustLevel.LIMITED,
            TrustLevel.STANDARD,
            TrustLevel.ELEVATED,
            TrustLevel.FULL,
        ]
        return order.index(self) < order.index(other)

    def __le__(self, other: "TrustLevel") -> bool:
        return self == other or self < other

    def __gt__(self, other: "TrustLevel") -> bool:
        return not self <= other

    def __ge__(self, other: "TrustLevel") -> bool:
        return not self < other


class ConfirmationResult(str, Enum):
    """承認結果"""

    APPROVED = "approved"
    """承認済み"""

    DENIED = "denied"
    """拒否"""

    PENDING = "pending"
    """保留中"""

    TIMEOUT = "timeout"
    """タイムアウト"""


@dataclass
class ConfirmationRequest:
    """承認リクエスト"""

    action_class: ActionClass
    """アクションの危険度"""

    trust_level: TrustLevel
    """実行者の信頼レベル"""

    tool_name: str
    """ツール名"""

    description: str
    """操作の説明"""

    parameters: dict = field(default_factory=dict)
    """パラメータ"""

    context: dict = field(default_factory=dict)
    """追加コンテキスト（ファイルパスなど）"""


@dataclass
class ConfirmationResponse:
    """承認レスポンス"""

    result: ConfirmationResult
    """承認結果"""

    reason: str = ""
    """理由（拒否時など）"""

    modified_parameters: dict | None = None
    """変更されたパラメータ（部分承認時）"""


# 承認マトリックス: (TrustLevel, ActionClass) -> 承認必要か
CONFIRMATION_MATRIX: dict[tuple[TrustLevel, ActionClass], bool] = {
    # UNTRUSTED: SAFEのみ自動承認
    (TrustLevel.UNTRUSTED, ActionClass.SAFE): False,
    (TrustLevel.UNTRUSTED, ActionClass.CAREFUL): True,
    (TrustLevel.UNTRUSTED, ActionClass.DANGEROUS): True,
    (TrustLevel.UNTRUSTED, ActionClass.CRITICAL): True,
    # LIMITED: CAREFUL以下自動承認
    (TrustLevel.LIMITED, ActionClass.SAFE): False,
    (TrustLevel.LIMITED, ActionClass.CAREFUL): False,
    (TrustLevel.LIMITED, ActionClass.DANGEROUS): True,
    (TrustLevel.LIMITED, ActionClass.CRITICAL): True,
    # STANDARD: DANGEROUS以下自動承認（ただしDANGEROUSは承認必要）
    (TrustLevel.STANDARD, ActionClass.SAFE): False,
    (TrustLevel.STANDARD, ActionClass.CAREFUL): False,
    (TrustLevel.STANDARD, ActionClass.DANGEROUS): True,  # 承認必要
    (TrustLevel.STANDARD, ActionClass.CRITICAL): True,
    # ELEVATED: CRITICAL以外自動承認
    (TrustLevel.ELEVATED, ActionClass.SAFE): False,
    (TrustLevel.ELEVATED, ActionClass.CAREFUL): False,
    (TrustLevel.ELEVATED, ActionClass.DANGEROUS): False,
    (TrustLevel.ELEVATED, ActionClass.CRITICAL): True,
    # FULL: 全て自動承認
    (TrustLevel.FULL, ActionClass.SAFE): False,
    (TrustLevel.FULL, ActionClass.CAREFUL): False,
    (TrustLevel.FULL, ActionClass.DANGEROUS): False,
    (TrustLevel.FULL, ActionClass.CRITICAL): False,
}


def requires_confirmation(trust_level: TrustLevel, action_class: ActionClass) -> bool:
    """承認が必要かどうか判定

    Args:
        trust_level: エージェントの信頼レベル
        action_class: アクションの危険度

    Returns:
        True: 承認が必要
        False: 自動承認可能
    """
    return CONFIRMATION_MATRIX.get((trust_level, action_class), True)


def get_max_action_class(trust_level: TrustLevel, auto_approve_only: bool = False) -> ActionClass:
    """信頼レベルで許可される最大のActionClass

    Args:
        trust_level: エージェントの信頼レベル
        auto_approve_only: True の場合、自動承認可能な範囲のみ

    Returns:
        最大許可ActionClass
    """
    if auto_approve_only:
        # 自動承認可能な最大レベル
        if trust_level == TrustLevel.FULL:
            return ActionClass.CRITICAL
        elif trust_level == TrustLevel.ELEVATED:
            return ActionClass.DANGEROUS
        elif trust_level >= TrustLevel.LIMITED:
            return ActionClass.CAREFUL
        else:
            return ActionClass.SAFE
    else:
        # 承認込みで許可される最大レベル
        if trust_level >= TrustLevel.STANDARD:
            return ActionClass.CRITICAL  # 承認があれば全て可能
        elif trust_level == TrustLevel.LIMITED:
            return ActionClass.CAREFUL
        else:
            return ActionClass.SAFE


class TrustManager:
    """信頼レベル管理"""

    def __init__(self):
        self._agent_trust: dict[str, TrustLevel] = {}
        self._tool_classes: dict[str, ActionClass] = {}
        self._confirmation_handler: Callable[[ConfirmationRequest], ConfirmationResponse] | None = (
            None
        )

    def set_agent_trust(self, agent_id: str, trust_level: TrustLevel) -> None:
        """エージェントの信頼レベルを設定"""
        self._agent_trust[agent_id] = trust_level

    def get_agent_trust(self, agent_id: str) -> TrustLevel:
        """エージェントの信頼レベルを取得"""
        return self._agent_trust.get(agent_id, TrustLevel.UNTRUSTED)

    def set_tool_class(self, tool_name: str, action_class: ActionClass) -> None:
        """ツールの危険度を設定"""
        self._tool_classes[tool_name] = action_class

    def get_tool_class(self, tool_name: str) -> ActionClass:
        """ツールの危険度を取得"""
        return self._tool_classes.get(tool_name, ActionClass.DANGEROUS)  # デフォルトは慎重に

    def set_confirmation_handler(
        self, handler: Callable[[ConfirmationRequest], ConfirmationResponse]
    ) -> None:
        """承認ハンドラを設定"""
        self._confirmation_handler = handler

    def check_permission(self, agent_id: str, tool_name: str) -> tuple[bool, bool]:
        """実行許可チェック

        Args:
            agent_id: エージェントID
            tool_name: ツール名

        Returns:
            (許可されるか, 承認が必要か)
        """
        trust_level = self.get_agent_trust(agent_id)
        action_class = self.get_tool_class(tool_name)
        max_allowed = get_max_action_class(trust_level, auto_approve_only=False)

        if action_class > max_allowed:
            return (False, False)  # 許可されない

        needs_confirm = requires_confirmation(trust_level, action_class)
        return (True, needs_confirm)

    def request_confirmation(
        self,
        agent_id: str,
        tool_name: str,
        description: str,
        parameters: dict | None = None,
        context: dict | None = None,
    ) -> ConfirmationResponse:
        """承認をリクエスト

        Args:
            agent_id: エージェントID
            tool_name: ツール名
            description: 操作の説明
            parameters: パラメータ
            context: 追加コンテキスト

        Returns:
            承認レスポンス
        """
        if self._confirmation_handler is None:
            # ハンドラがない場合はデフォルトで拒否
            return ConfirmationResponse(
                result=ConfirmationResult.DENIED, reason="No confirmation handler configured"
            )

        request = ConfirmationRequest(
            action_class=self.get_tool_class(tool_name),
            trust_level=self.get_agent_trust(agent_id),
            tool_name=tool_name,
            description=description,
            parameters=parameters or {},
            context=context or {},
        )

        return self._confirmation_handler(request)


def create_default_tool_classes() -> dict[str, ActionClass]:
    """デフォルトのツール危険度分類を作成"""
    return {
        # SAFE: 読み取り専用
        "read_file": ActionClass.SAFE,
        "list_dir": ActionClass.SAFE,
        "search": ActionClass.SAFE,
        "get_status": ActionClass.SAFE,
        # CAREFUL: 軽微な変更
        "create_file": ActionClass.CAREFUL,
        "edit_file": ActionClass.CAREFUL,
        "mkdir": ActionClass.CAREFUL,
        # DANGEROUS: 重大な変更
        "delete_file": ActionClass.DANGEROUS,
        "execute_command": ActionClass.DANGEROUS,
        "http_request": ActionClass.DANGEROUS,
        # CRITICAL: 回復困難
        "rm_rf": ActionClass.CRITICAL,
        "sudo": ActionClass.CRITICAL,
        "modify_credentials": ActionClass.CRITICAL,
    }
