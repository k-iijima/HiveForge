"""Decision Protocol イベント型のテスト

外部フィードバック対応: 意思決定ライフサイクル（提案→決定→適用→上書き）を追跡する。
"""

import pytest

from hiveforge.core.events import (
    EVENT_TYPE_MAP,
    BaseEvent,
    DecisionAppliedEvent,
    DecisionSupersededEvent,
    EventType,
    ProposalCreatedEvent,
    parse_event,
)


class TestDecisionProtocolEventTypes:
    """Decision Protocol イベント型がEventTypeに定義されているかテスト"""

    def test_proposal_created_event_type_exists(self):
        """PROPOSAL_CREATEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.PROPOSAL_CREATED

        # Assert
        assert event_type.value == "decision.proposal.created"

    def test_decision_applied_event_type_exists(self):
        """DECISION_APPLIEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.DECISION_APPLIED

        # Assert
        assert event_type.value == "decision.applied"

    def test_decision_superseded_event_type_exists(self):
        """DECISION_SUPERSEDEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.DECISION_SUPERSEDED

        # Assert
        assert event_type.value == "decision.superseded"

    def test_decision_recorded_event_type_already_exists(self):
        """DECISION_RECORDED（既存）イベント型が存在する"""
        # Arrange & Act
        event_type = EventType.DECISION_RECORDED

        # Assert
        assert event_type.value == "decision.recorded"


class TestProposalCreatedEvent:
    """ProposalCreatedEvent のテスト"""

    def test_create_proposal_created_event(self):
        """提案作成イベントを生成できる

        提案には提案者、タイトル、説明が含まれる。
        """
        # Arrange
        payload = {
            "proposal_id": "prop-001",
            "proposer": "ui-ux-colony",
            "title": "モバイルファースト設計の採用",
            "description": "レスポンシブデザインよりモバイルファーストを優先する",
            "options": ["モバイルファースト", "デスクトップファースト", "両方並行"],
        }

        # Act
        event = ProposalCreatedEvent(
            actor="ui-ux-queen",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.PROPOSAL_CREATED
        assert event.payload["proposal_id"] == "prop-001"
        assert event.payload["proposer"] == "ui-ux-colony"
        assert event.payload["title"] == "モバイルファースト設計の採用"
        assert len(event.payload["options"]) == 3

    def test_proposal_created_event_is_immutable(self):
        """ProposalCreatedEventはイミュータブル"""
        # Arrange
        event = ProposalCreatedEvent(
            payload={"proposal_id": "prop-001", "title": "test"},
        )

        # Act & Assert
        with pytest.raises(Exception):  # ValidationError or frozen error
            event.payload = {"proposal_id": "changed"}


class TestDecisionAppliedEvent:
    """DecisionAppliedEvent のテスト"""

    def test_create_decision_applied_event(self):
        """決定適用イベントを生成できる

        決定が実際に適用（実装）された時に発行する。
        """
        # Arrange
        payload = {
            "decision_id": "dec-001",
            "proposal_id": "prop-001",
            "applied_by": "worker-bee-a",
            "applied_to": ["src/components/Layout.tsx", "src/styles/mobile.css"],
        }

        # Act
        event = DecisionAppliedEvent(
            actor="worker-bee-a",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.DECISION_APPLIED
        assert event.payload["decision_id"] == "dec-001"
        assert event.payload["applied_by"] == "worker-bee-a"
        assert len(event.payload["applied_to"]) == 2


class TestDecisionSupersededEvent:
    """DecisionSupersededEvent のテスト"""

    def test_create_decision_superseded_event(self):
        """決定上書きイベントを生成できる

        以前の決定が新しい決定で置き換えられた時に発行する。
        """
        # Arrange
        payload = {
            "old_decision_id": "dec-001",
            "new_decision_id": "dec-002",
            "reason": "顧客要望により仕様変更",
        }

        # Act
        event = DecisionSupersededEvent(
            actor="beekeeper",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.DECISION_SUPERSEDED
        assert event.payload["old_decision_id"] == "dec-001"
        assert event.payload["new_decision_id"] == "dec-002"
        assert event.payload["reason"] == "顧客要望により仕様変更"


class TestDecisionProtocolEventTypeMap:
    """EVENT_TYPE_MAP に Decision Protocol イベントが登録されているかテスト"""

    def test_proposal_created_in_event_type_map(self):
        """PROPOSAL_CREATEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.PROPOSAL_CREATED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.PROPOSAL_CREATED] == ProposalCreatedEvent

    def test_decision_applied_in_event_type_map(self):
        """DECISION_APPLIEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.DECISION_APPLIED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.DECISION_APPLIED] == DecisionAppliedEvent

    def test_decision_superseded_in_event_type_map(self):
        """DECISION_SUPERSEDEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.DECISION_SUPERSEDED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.DECISION_SUPERSEDED] == DecisionSupersededEvent


class TestDecisionProtocolParseEvent:
    """parse_event で Decision Protocol イベントが正しくパースされるかテスト"""

    def test_parse_proposal_created_event(self):
        """PROPOSAL_CREATEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "decision.proposal.created",
            "actor": "ui-ux-queen",
            "payload": {"proposal_id": "prop-001", "title": "test"},
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ProposalCreatedEvent)
        assert event.type == EventType.PROPOSAL_CREATED

    def test_parse_decision_applied_event(self):
        """DECISION_APPLIEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "decision.applied",
            "actor": "worker-bee",
            "payload": {"decision_id": "dec-001"},
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, DecisionAppliedEvent)
        assert event.type == EventType.DECISION_APPLIED

    def test_parse_decision_superseded_event(self):
        """DECISION_SUPERSEDEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "decision.superseded",
            "actor": "beekeeper",
            "payload": {"old_decision_id": "dec-001", "new_decision_id": "dec-002"},
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, DecisionSupersededEvent)
        assert event.type == EventType.DECISION_SUPERSEDED
