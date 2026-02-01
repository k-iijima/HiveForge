"""Conference エンティティ化テスト

外部フィードバック対応: conference_idを中心としたイベント束ね。
"""


from hiveforge.core.events import (
    ConferenceEndedEvent,
    ConferenceStartedEvent,
    EventType,
    parse_event,
)


class TestConferenceStartedEvent:
    """ConferenceStartedEvent のテスト"""

    def test_create_conference_started_with_conference_id(self):
        """conference_idを含むConferenceStartedEventを作成できる"""
        # Arrange & Act
        event = ConferenceStartedEvent(
            actor="user",
            payload={
                "conference_id": "01HXYZ123456",  # 必須
                "hive_id": "01HWXY654321",
                "topic": "ECサイト基本設計",
                "participants": ["ui-colony", "api-colony", "data-colony"],
                "initiated_by": "user",
            },
        )

        # Assert
        assert event.type == EventType.CONFERENCE_STARTED
        assert event.payload["conference_id"] == "01HXYZ123456"
        assert event.payload["hive_id"] == "01HWXY654321"
        assert len(event.payload["participants"]) == 3

    def test_parse_conference_started(self):
        """ConferenceStartedEventをパースできる"""
        # Arrange
        data = {
            "type": "conference.started",
            "actor": "beekeeper",
            "payload": {
                "conference_id": "conf-001",
                "hive_id": "hive-001",
                "topic": "認証方式の決定",
                "participants": ["auth-colony"],
                "initiated_by": "beekeeper",
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ConferenceStartedEvent)
        assert event.payload["initiated_by"] == "beekeeper"


class TestConferenceEndedEvent:
    """ConferenceEndedEvent のテスト"""

    def test_create_conference_ended_with_summary(self):
        """サマリ付きConferenceEndedEventを作成できる"""
        # Arrange & Act
        event = ConferenceEndedEvent(
            actor="user",
            payload={
                "conference_id": "01HXYZ123456",
                "duration_seconds": 1800,
                "decisions_made": ["decision-001", "decision-002"],
                "summary": "モバイルファースト、Stripe決済で合意",
                "ended_by": "user",
            },
        )

        # Assert
        assert event.type == EventType.CONFERENCE_ENDED
        assert event.payload["conference_id"] == "01HXYZ123456"
        assert event.payload["duration_seconds"] == 1800
        assert len(event.payload["decisions_made"]) == 2
        assert "Stripe" in event.payload["summary"]

    def test_parse_conference_ended(self):
        """ConferenceEndedEventをパースできる"""
        # Arrange
        data = {
            "type": "conference.ended",
            "actor": "user",
            "payload": {
                "conference_id": "conf-002",
                "duration_seconds": 3600,
                "decisions_made": [],
                "summary": "合意に至らず、再検討",
                "ended_by": "user",
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ConferenceEndedEvent)
        assert event.payload["ended_by"] == "user"


class TestConferenceInitiatedBy:
    """initiated_by / ended_by の値パターンテスト"""

    def test_initiated_by_user(self):
        """initiated_by = 'user' パターン"""
        event = ConferenceStartedEvent(
            actor="user",
            payload={
                "conference_id": "c-001",
                "hive_id": "h-001",
                "topic": "test",
                "participants": [],
                "initiated_by": "user",
            },
        )
        assert event.payload["initiated_by"] == "user"

    def test_initiated_by_beekeeper(self):
        """initiated_by = 'beekeeper' パターン"""
        event = ConferenceStartedEvent(
            actor="beekeeper",
            payload={
                "conference_id": "c-002",
                "hive_id": "h-001",
                "topic": "緊急会議",
                "participants": ["colony-a"],
                "initiated_by": "beekeeper",
            },
        )
        assert event.payload["initiated_by"] == "beekeeper"


class TestConferenceIdRequired:
    """conference_id が中心となることの確認テスト"""

    def test_conference_events_have_conference_id_in_payload(self):
        """Conference関連イベントはpayloadにconference_idを持つ"""
        # Arrange
        started = ConferenceStartedEvent(
            actor="user",
            payload={
                "conference_id": "conf-123",
                "hive_id": "h-001",
                "topic": "test",
                "participants": [],
                "initiated_by": "user",
            },
        )
        ended = ConferenceEndedEvent(
            actor="user",
            payload={
                "conference_id": "conf-123",
                "duration_seconds": 100,
                "decisions_made": [],
                "summary": "done",
                "ended_by": "user",
            },
        )

        # Assert
        assert "conference_id" in started.payload
        assert "conference_id" in ended.payload
        assert started.payload["conference_id"] == ended.payload["conference_id"]

    def test_conference_can_be_linked_by_conference_id(self):
        """conference_idでイベントを紐付けられる"""
        # Arrange: 同じconference_idを持つ複数のイベント
        conference_id = "01HXYZ789012"

        started = ConferenceStartedEvent(
            actor="user",
            payload={
                "conference_id": conference_id,
                "hive_id": "h-001",
                "topic": "API設計レビュー",
                "participants": ["api-colony", "frontend-colony"],
                "initiated_by": "user",
            },
        )
        ended = ConferenceEndedEvent(
            actor="user",
            payload={
                "conference_id": conference_id,
                "duration_seconds": 2700,
                "decisions_made": ["d-001"],
                "summary": "OpenAPI仕様で合意",
                "ended_by": "user",
            },
        )

        # Act: conference_idでグループ化
        events = [started, ended]
        grouped = {
            e.payload["conference_id"]: [
                ev for ev in events if ev.payload["conference_id"] == e.payload["conference_id"]
            ]
            for e in events
        }

        # Assert
        assert len(grouped[conference_id]) == 2
