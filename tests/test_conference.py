"""Conference ライフサイクルイベントのテスト

外部フィードバック対応: 会議（Conference）の開始・終了を追跡する。
"""

import pytest

from hiveforge.core.events import (
    EVENT_TYPE_MAP,
    ConferenceEndedEvent,
    ConferenceStartedEvent,
    EventType,
    parse_event,
)


class TestConferenceEventTypes:
    """Conference イベント型がEventTypeに定義されているかテスト"""

    def test_conference_started_event_type_exists(self):
        """CONFERENCE_STARTEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.CONFERENCE_STARTED

        # Assert
        assert event_type.value == "conference.started"

    def test_conference_ended_event_type_exists(self):
        """CONFERENCE_ENDEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.CONFERENCE_ENDED

        # Assert
        assert event_type.value == "conference.ended"


class TestConferenceStartedEvent:
    """ConferenceStartedEvent のテスト"""

    def test_create_conference_started_event(self):
        """会議開始イベントを生成できる

        会議にはID、参加Colonyリスト、議題が含まれる。
        """
        # Arrange
        payload = {
            "conference_id": "conf-001",
            "hive_id": "hive-abc",
            "participants": ["ui-ux-colony", "api-colony", "data-colony"],
            "topic": "ECサイト基本設計の方針決定",
            "initiated_by": "beekeeper",
        }

        # Act
        event = ConferenceStartedEvent(
            actor="beekeeper",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.CONFERENCE_STARTED
        assert event.payload["conference_id"] == "conf-001"
        assert len(event.payload["participants"]) == 3
        assert event.payload["topic"] == "ECサイト基本設計の方針決定"

    def test_conference_started_event_is_immutable(self):
        """ConferenceStartedEventはイミュータブル"""
        # Arrange
        event = ConferenceStartedEvent(
            payload={"conference_id": "conf-001", "topic": "test"},
        )

        # Act & Assert
        with pytest.raises(Exception):
            event.payload = {"conference_id": "changed"}


class TestConferenceEndedEvent:
    """ConferenceEndedEvent のテスト"""

    def test_create_conference_ended_event(self):
        """会議終了イベントを生成できる

        会議終了時には決定事項のサマリーを含む。
        """
        # Arrange
        payload = {
            "conference_id": "conf-001",
            "duration_seconds": 1800,  # 30分
            "decisions_made": ["dec-001", "dec-002"],
            "summary": "モバイルファースト採用、Stripe決済に決定",
            "ended_by": "beekeeper",
        }

        # Act
        event = ConferenceEndedEvent(
            actor="beekeeper",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.CONFERENCE_ENDED
        assert event.payload["conference_id"] == "conf-001"
        assert event.payload["duration_seconds"] == 1800
        assert len(event.payload["decisions_made"]) == 2

    def test_conference_ended_with_no_decisions(self):
        """決定事項なしで会議が終了した場合"""
        # Arrange
        payload = {
            "conference_id": "conf-002",
            "duration_seconds": 600,
            "decisions_made": [],
            "summary": "追加情報が必要。次回に持ち越し。",
            "ended_by": "user",
        }

        # Act
        event = ConferenceEndedEvent(
            actor="user",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.CONFERENCE_ENDED
        assert event.payload["decisions_made"] == []


class TestConferenceEventTypeMap:
    """EVENT_TYPE_MAP に Conference イベントが登録されているかテスト"""

    def test_conference_started_in_event_type_map(self):
        """CONFERENCE_STARTEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.CONFERENCE_STARTED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.CONFERENCE_STARTED] == ConferenceStartedEvent

    def test_conference_ended_in_event_type_map(self):
        """CONFERENCE_ENDEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.CONFERENCE_ENDED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.CONFERENCE_ENDED] == ConferenceEndedEvent


class TestConferenceParseEvent:
    """parse_event で Conference イベントが正しくパースされるかテスト"""

    def test_parse_conference_started_event(self):
        """CONFERENCE_STARTEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "conference.started",
            "actor": "beekeeper",
            "payload": {"conference_id": "conf-001", "topic": "設計レビュー"},
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ConferenceStartedEvent)
        assert event.type == EventType.CONFERENCE_STARTED

    def test_parse_conference_ended_event(self):
        """CONFERENCE_ENDEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "conference.ended",
            "actor": "beekeeper",
            "payload": {"conference_id": "conf-001", "summary": "完了"},
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ConferenceEndedEvent)
        assert event.type == EventType.CONFERENCE_ENDED
