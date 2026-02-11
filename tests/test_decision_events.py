"""Decision イベントの scope/owner/supersedes テスト

外部フィードバック対応: 誰が記録したか、どこに効くか、何を上書きしたかを追跡。
"""

from colonyforge.core.events import (
    DecisionAppliedEvent,
    DecisionRecordedEvent,
    DecisionScope,
    DecisionSupersededEvent,
    EventType,
    RiskLevel,
    parse_event,
)


class TestDecisionScopeEnum:
    """DecisionScope 列挙型のテスト"""

    def test_decision_scope_enum_exists(self):
        """DecisionScope列挙型が存在する"""
        # Assert
        assert DecisionScope is not None

    def test_decision_scope_has_hive(self):
        """HIVE: Hive全体に適用"""
        assert DecisionScope.HIVE == "hive"

    def test_decision_scope_has_colony(self):
        """COLONY: 特定のColonyに適用"""
        assert DecisionScope.COLONY == "colony"

    def test_decision_scope_has_run(self):
        """RUN: 特定のRunに適用"""
        assert DecisionScope.RUN == "run"

    def test_decision_scope_has_task(self):
        """TASK: 特定のTaskに適用"""
        assert DecisionScope.TASK == "task"


class TestRiskLevelEnum:
    """RiskLevel 列挙型のテスト"""

    def test_risk_level_enum_exists(self):
        """RiskLevel列挙型が存在する"""
        assert RiskLevel is not None

    def test_risk_level_has_low(self):
        """LOW: 低リスク"""
        assert RiskLevel.LOW == "low"

    def test_risk_level_has_medium(self):
        """MEDIUM: 中リスク"""
        assert RiskLevel.MEDIUM == "medium"

    def test_risk_level_has_high(self):
        """HIGH: 高リスク"""
        assert RiskLevel.HIGH == "high"


class TestDecisionRecordedEventPayload:
    """DecisionRecordedEvent のペイロード拡張テスト"""

    def test_create_decision_with_scope_and_owner(self):
        """scope/recorded_byを含むDecisionRecordedEventを作成できる"""
        # Arrange & Act
        event = DecisionRecordedEvent(
            actor="user",
            payload={
                "decision_id": "decision-001",
                "hive_id": "01HWXY123456",
                "scope": DecisionScope.COLONY.value,
                "scope_id": "api-colony",
                "recorded_by": "user",
                "choice": "REST APIを採用",
                "rationale": "チームの経験が豊富",
            },
        )

        # Assert
        assert event.payload["scope"] == "colony"
        assert event.payload["scope_id"] == "api-colony"
        assert event.payload["recorded_by"] == "user"

    def test_create_decision_with_supersedes(self):
        """supersedes_decision_idを含むDecisionRecordedEvent（上書き）"""
        # Arrange & Act
        event = DecisionRecordedEvent(
            actor="user",
            payload={
                "decision_id": "decision-002",
                "hive_id": "01HWXY123456",
                "scope": DecisionScope.HIVE.value,
                "scope_id": "01HWXY123456",
                "recorded_by": "user",
                "supersedes_decision_id": "decision-001",  # 上書き
                "choice": "GraphQLに変更",
                "rationale": "フロントエンド要件の変更",
            },
        )

        # Assert
        assert event.payload["supersedes_decision_id"] == "decision-001"

    def test_create_decision_with_impact(self):
        """impactを含むDecisionRecordedEvent"""
        # Arrange & Act
        event = DecisionRecordedEvent(
            actor="beekeeper",
            payload={
                "decision_id": "decision-003",
                "hive_id": "01HWXY123456",
                "scope": DecisionScope.COLONY.value,
                "scope_id": "data-colony",
                "recorded_by": "beekeeper",
                "choice": "PostgreSQLを採用",
                "rationale": "ACID準拠が必要",
                "impact": {
                    "affected_colonies": ["api-colony", "data-colony"],
                    "estimated_effort_hours": 16,
                    "risk_level": RiskLevel.MEDIUM.value,
                },
            },
        )

        # Assert
        assert event.payload["impact"]["risk_level"] == "medium"
        assert event.payload["impact"]["estimated_effort_hours"] == 16
        assert len(event.payload["impact"]["affected_colonies"]) == 2

    def test_create_decision_with_rollback_plan(self):
        """rollback_planを含むDecisionRecordedEvent"""
        # Arrange & Act
        event = DecisionRecordedEvent(
            actor="user",
            payload={
                "decision_id": "decision-004",
                "hive_id": "01HWXY123456",
                "scope": DecisionScope.RUN.value,
                "scope_id": "run-001",
                "recorded_by": "user",
                "choice": "新しいデプロイ方式を試行",
                "rationale": "効率化のため",
                "rollback_plan": "git revert abc123 && kubectl rollback deployment/app",
            },
        )

        # Assert
        assert "git revert" in event.payload["rollback_plan"]


class TestDecisionAppliedEventPayload:
    """DecisionAppliedEvent のペイロード拡張テスト"""

    def test_parse_decision_applied_with_scope(self):
        """DecisionAppliedEventをパースできる"""
        # Arrange
        data = {
            "type": "decision.applied",
            "actor": "beekeeper",
            "payload": {
                "decision_id": "decision-001",
                "hive_id": "01HWXY123456",
                "scope": "colony",
                "scope_id": "api-colony",
                "recorded_by": "queen:api-colony",
                "applied_at": "2026-02-01T12:00:00Z",
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, DecisionAppliedEvent)
        assert event.payload["recorded_by"] == "queen:api-colony"


class TestDecisionSupersededEvent:
    """DecisionSupersededEvent のテスト"""

    def test_create_superseded_event(self):
        """DecisionSupersededEventを作成できる"""
        # Arrange & Act
        event = DecisionSupersededEvent(
            actor="user",
            payload={
                "old_decision_id": "decision-001",
                "new_decision_id": "decision-002",
                "reason": "セキュリティ要件の追加により方針変更",
                "recorded_by": "user",
            },
        )

        # Assert
        assert event.type == EventType.DECISION_SUPERSEDED
        assert event.payload["old_decision_id"] == "decision-001"
        assert event.payload["new_decision_id"] == "decision-002"

    def test_parse_superseded_event(self):
        """DecisionSupersededEventをパースできる"""
        # Arrange
        data = {
            "type": "decision.superseded",
            "actor": "beekeeper",
            "payload": {
                "old_decision_id": "dec-old",
                "new_decision_id": "dec-new",
                "reason": "要件変更",
                "recorded_by": "beekeeper",
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, DecisionSupersededEvent)


class TestRecordedByValues:
    """recorded_by の値パターンテスト"""

    def test_recorded_by_user(self):
        """recorded_by = 'user' パターン"""
        event = DecisionRecordedEvent(
            actor="user",
            payload={
                "decision_id": "d-001",
                "hive_id": "h-001",
                "recorded_by": "user",
                "choice": "test",
                "rationale": "test",
            },
        )
        assert event.payload["recorded_by"] == "user"

    def test_recorded_by_beekeeper(self):
        """recorded_by = 'beekeeper' パターン"""
        event = DecisionRecordedEvent(
            actor="beekeeper",
            payload={
                "decision_id": "d-002",
                "hive_id": "h-001",
                "recorded_by": "beekeeper",
                "choice": "test",
                "rationale": "test",
            },
        )
        assert event.payload["recorded_by"] == "beekeeper"

    def test_recorded_by_queen_pattern(self):
        """recorded_by = 'queen:{colony_id}' パターン"""
        event = DecisionRecordedEvent(
            actor="queen:api-colony",
            payload={
                "decision_id": "d-003",
                "hive_id": "h-001",
                "recorded_by": "queen:api-colony",
                "choice": "test",
                "rationale": "test",
            },
        )
        assert event.payload["recorded_by"].startswith("queen:")
