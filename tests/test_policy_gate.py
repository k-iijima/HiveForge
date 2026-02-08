"""Policy Gate（中央集権的アクション判定）テスト

外部フィードバック対応: Action Classの判定ロジックを中央集権化し、散在を防ぐ。
"""

from hiveforge.core.models.action_class import ActionClass, TrustLevel
from hiveforge.core.policy_gate import (
    PolicyDecision,
    PolicyGate,
    policy_gate,
)


class TestPolicyDecisionEnum:
    """PolicyDecision 列挙型のテスト"""

    def test_policy_decision_enum_exists(self):
        """PolicyDecision列挙型が存在する"""
        assert PolicyDecision is not None

    def test_policy_decision_has_allow(self):
        """ALLOW: 実行許可"""
        assert PolicyDecision.ALLOW == "allow"

    def test_policy_decision_has_require_approval(self):
        """REQUIRE_APPROVAL: 承認必要"""
        assert PolicyDecision.REQUIRE_APPROVAL == "require_approval"

    def test_policy_decision_has_deny(self):
        """DENY: 拒否"""
        assert PolicyDecision.DENY == "deny"


class TestPolicyGateFunction:
    """policy_gate 関数のテスト"""

    def test_policy_gate_function_exists(self):
        """policy_gate関数が存在する"""
        assert callable(policy_gate)

    def test_read_only_always_allowed(self):
        """READ_ONLY アクションは常にALLOW"""
        # Arrange & Act
        decision = policy_gate(
            actor="worker:001",
            action_class=ActionClass.READ_ONLY,
            trust_level=TrustLevel.REPORT_ONLY,
            scope="task",
            scope_id="task-001",
        )

        # Assert
        assert decision == PolicyDecision.ALLOW

    def test_level0_reversible_requires_approval(self):
        """Level 0 + REVERSIBLE は承認が必要"""
        # Arrange & Act
        decision = policy_gate(
            actor="worker:001",
            action_class=ActionClass.REVERSIBLE,
            trust_level=TrustLevel.REPORT_ONLY,
            scope="task",
            scope_id="task-001",
        )

        # Assert
        assert decision == PolicyDecision.REQUIRE_APPROVAL

    def test_level0_irreversible_denied(self):
        """Level 0 + IRREVERSIBLE は拒否"""
        # Arrange & Act
        decision = policy_gate(
            actor="worker:001",
            action_class=ActionClass.IRREVERSIBLE,
            trust_level=TrustLevel.REPORT_ONLY,
            scope="task",
            scope_id="task-001",
        )

        # Assert
        assert decision == PolicyDecision.DENY

    def test_level1_reversible_allowed(self):
        """Level 1 + REVERSIBLE はALLOW"""
        # Arrange & Act
        decision = policy_gate(
            actor="worker:001",
            action_class=ActionClass.REVERSIBLE,
            trust_level=TrustLevel.PROPOSE_CONFIRM,
            scope="task",
            scope_id="task-001",
        )

        # Assert
        assert decision == PolicyDecision.ALLOW

    def test_level1_irreversible_requires_approval(self):
        """Level 1 + IRREVERSIBLE は承認が必要"""
        # Arrange & Act
        decision = policy_gate(
            actor="worker:001",
            action_class=ActionClass.IRREVERSIBLE,
            trust_level=TrustLevel.PROPOSE_CONFIRM,
            scope="run",
            scope_id="run-001",
        )

        # Assert
        assert decision == PolicyDecision.REQUIRE_APPROVAL

    def test_level2_irreversible_allowed(self):
        """Level 2 + IRREVERSIBLE はALLOW"""
        # Arrange & Act
        decision = policy_gate(
            actor="queen:api-colony",
            action_class=ActionClass.IRREVERSIBLE,
            trust_level=TrustLevel.AUTO_NOTIFY,
            scope="colony",
            scope_id="api-colony",
        )

        # Assert
        assert decision == PolicyDecision.ALLOW

    def test_level3_irreversible_allowed(self):
        """Level 3 + IRREVERSIBLE はALLOW"""
        # Arrange & Act
        decision = policy_gate(
            actor="beekeeper",
            action_class=ActionClass.IRREVERSIBLE,
            trust_level=TrustLevel.FULL_DELEGATION,
            scope="hive",
            scope_id="hive-001",
        )

        # Assert
        assert decision == PolicyDecision.ALLOW


class TestPolicyGateWithContext:
    """context パラメータを使ったテスト"""

    def test_context_can_include_tool_name(self):
        """contextにツール名を含められる"""
        # Arrange & Act
        decision = policy_gate(
            actor="worker:001",
            action_class=ActionClass.READ_ONLY,
            trust_level=TrustLevel.PROPOSE_CONFIRM,
            scope="task",
            scope_id="task-001",
            context={"tool_name": "read_file", "path": "/workspace/README.md"},
        )

        # Assert
        assert decision == PolicyDecision.ALLOW


class TestPolicyGateClass:
    """PolicyGate クラスのテスト（設定カスタマイズ用）"""

    def test_policy_gate_class_exists(self):
        """PolicyGateクラスが存在する"""
        assert PolicyGate is not None

    def test_policy_gate_with_custom_config(self):
        """カスタム設定でPolicyGateを作成できる"""
        # Arrange
        config = {
            "level3_irreversible_requires_approval": True,
        }
        gate = PolicyGate(config=config)

        # Act
        decision = gate.evaluate(
            actor="beekeeper",
            action_class=ActionClass.IRREVERSIBLE,
            trust_level=TrustLevel.FULL_DELEGATION,
            scope="hive",
            scope_id="hive-001",
        )

        # Assert: 設定でLevel 3 + IRREVERSIBLEも承認必須
        assert decision == PolicyDecision.REQUIRE_APPROVAL

    def test_policy_gate_default_config(self):
        """デフォルト設定のPolicyGate"""
        # Arrange
        gate = PolicyGate()

        # Act
        decision = gate.evaluate(
            actor="worker:001",
            action_class=ActionClass.READ_ONLY,
            trust_level=TrustLevel.REPORT_ONLY,
            scope="task",
            scope_id="task-001",
        )

        # Assert
        assert decision == PolicyDecision.ALLOW


class TestActorTypes:
    """actor パラメータの各パターンテスト"""

    def test_actor_user(self):
        """actor = 'user' パターン"""
        decision = policy_gate(
            actor="user",
            action_class=ActionClass.REVERSIBLE,
            trust_level=TrustLevel.FULL_DELEGATION,
            scope="hive",
        )
        assert decision == PolicyDecision.ALLOW

    def test_actor_beekeeper(self):
        """actor = 'beekeeper' パターン"""
        decision = policy_gate(
            actor="beekeeper",
            action_class=ActionClass.REVERSIBLE,
            trust_level=TrustLevel.AUTO_NOTIFY,
            scope="hive",
        )
        assert decision == PolicyDecision.ALLOW

    def test_actor_queen_pattern(self):
        """actor = 'queen:{colony_id}' パターン"""
        decision = policy_gate(
            actor="queen:api-colony",
            action_class=ActionClass.READ_ONLY,
            trust_level=TrustLevel.PROPOSE_CONFIRM,
            scope="colony",
            scope_id="api-colony",
        )
        assert decision == PolicyDecision.ALLOW

    def test_actor_worker_pattern(self):
        """actor = 'worker:{worker_id}' パターン"""
        decision = policy_gate(
            actor="worker:worker-001",
            action_class=ActionClass.READ_ONLY,
            trust_level=TrustLevel.REPORT_ONLY,
            scope="task",
            scope_id="task-001",
        )
        assert decision == PolicyDecision.ALLOW
