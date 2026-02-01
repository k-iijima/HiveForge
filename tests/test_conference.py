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
from hiveforge.core.state.conference import (
    ConferenceProjection,
    ConferenceState,
    ConferenceStore,
    build_conference_projection,
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
        """会議開始イベントはイミュータブル"""
        # Arrange
        event = ConferenceStartedEvent(
            payload={"conference_id": "conf-001", "topic": "test"},
        )

        # Act & Assert: frozen modelの変更試行はValidationErrorを投げる
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


class TestBuildConferenceProjection:
    """build_conference_projection のテスト"""

    def test_build_projection_from_started_event(self):
        """CONFERENCE_STARTEDイベントからProjectionを構築できる"""
        # Arrange
        event = ConferenceStartedEvent(
            actor="beekeeper",
            payload={
                "conference_id": "conf-001",
                "hive_id": "hive-abc",
                "topic": "設計レビュー",
                "participants": ["ui-colony", "api-colony"],
                "initiated_by": "beekeeper",
            },
        )

        # Act
        projection = build_conference_projection([event], "conf-001")

        # Assert
        assert projection is not None
        assert projection.conference_id == "conf-001"
        assert projection.hive_id == "hive-abc"
        assert projection.topic == "設計レビュー"
        assert projection.state == ConferenceState.ACTIVE
        assert len(projection.participants) == 2

    def test_build_projection_with_ended_event(self):
        """CONFERENCE_ENDEDイベントでProjectionが更新される"""
        # Arrange
        started_event = ConferenceStartedEvent(
            actor="beekeeper",
            payload={
                "conference_id": "conf-001",
                "hive_id": "hive-abc",
                "topic": "設計レビュー",
                "participants": ["ui-colony"],
            },
        )
        ended_event = ConferenceEndedEvent(
            actor="beekeeper",
            payload={
                "conference_id": "conf-001",
                "duration_seconds": 1800,
                "decisions_made": ["dec-001"],
                "summary": "設計完了",
            },
        )

        # Act
        projection = build_conference_projection([started_event, ended_event], "conf-001")

        # Assert
        assert projection is not None
        assert projection.state == ConferenceState.ENDED
        assert projection.summary == "設計完了"
        assert projection.duration_seconds == 1800
        assert projection.decisions_made == ["dec-001"]

    def test_build_projection_returns_none_for_nonexistent(self):
        """存在しない会議IDではNoneを返す"""
        # Arrange
        event = ConferenceStartedEvent(
            actor="beekeeper",
            payload={"conference_id": "conf-001", "topic": "test"},
        )

        # Act
        projection = build_conference_projection([event], "conf-999")

        # Assert
        assert projection is None

    def test_build_projection_ignores_ended_without_started(self):
        """STARTEDなしでENDEDのみの場合はNoneを返す"""
        # Arrange
        ended_event = ConferenceEndedEvent(
            actor="beekeeper",
            payload={"conference_id": "conf-001", "summary": "完了"},
        )

        # Act
        projection = build_conference_projection([ended_event], "conf-001")

        # Assert
        assert projection is None


class TestConferenceStore:
    """ConferenceStore のテスト"""

    def test_add_and_get(self):
        """会議の追加と取得ができる"""
        # Arrange
        store = ConferenceStore()
        projection = ConferenceProjection(
            conference_id="conf-001",
            hive_id="hive-abc",
            topic="テスト会議",
            participants=["colony-a"],
            state=ConferenceState.ACTIVE,
        )

        # Act
        store.add(projection)
        result = store.get("conf-001")

        # Assert
        assert result is not None
        assert result.conference_id == "conf-001"
        assert result.topic == "テスト会議"

    def test_get_nonexistent_returns_none(self):
        """存在しない会議はNoneを返す"""
        # Arrange
        store = ConferenceStore()

        # Act
        result = store.get("nonexistent")

        # Assert
        assert result is None

    def test_list_all(self):
        """全会議をリストできる"""
        # Arrange
        store = ConferenceStore()
        store.add(
            ConferenceProjection(
                conference_id="conf-001",
                hive_id="hive-a",
                topic="会議1",
                participants=[],
                state=ConferenceState.ACTIVE,
            )
        )
        store.add(
            ConferenceProjection(
                conference_id="conf-002",
                hive_id="hive-a",
                topic="会議2",
                participants=[],
                state=ConferenceState.ENDED,
            )
        )

        # Act
        result = store.list_all()

        # Assert
        assert len(result) == 2

    def test_list_active(self):
        """アクティブな会議のみリストできる"""
        # Arrange
        store = ConferenceStore()
        store.add(
            ConferenceProjection(
                conference_id="conf-001",
                hive_id="hive-a",
                topic="会議1",
                participants=[],
                state=ConferenceState.ACTIVE,
            )
        )
        store.add(
            ConferenceProjection(
                conference_id="conf-002",
                hive_id="hive-a",
                topic="会議2",
                participants=[],
                state=ConferenceState.ENDED,
            )
        )

        # Act
        result = store.list_active()

        # Assert
        assert len(result) == 1
        assert result[0].conference_id == "conf-001"

    def test_list_by_hive(self):
        """Hive IDで会議をフィルタできる"""
        # Arrange
        store = ConferenceStore()
        store.add(
            ConferenceProjection(
                conference_id="conf-001",
                hive_id="hive-a",
                topic="会議1",
                participants=[],
                state=ConferenceState.ACTIVE,
            )
        )
        store.add(
            ConferenceProjection(
                conference_id="conf-002",
                hive_id="hive-b",
                topic="会議2",
                participants=[],
                state=ConferenceState.ACTIVE,
            )
        )

        # Act
        result = store.list_by_hive("hive-a")

        # Assert
        assert len(result) == 1
        assert result[0].conference_id == "conf-001"

    def test_update(self):
        """会議を更新できる"""
        # Arrange
        store = ConferenceStore()
        projection = ConferenceProjection(
            conference_id="conf-001",
            hive_id="hive-a",
            topic="会議1",
            participants=[],
            state=ConferenceState.ACTIVE,
        )
        store.add(projection)

        # Act
        projection.state = ConferenceState.ENDED
        projection.summary = "完了"
        store.update(projection)
        result = store.get("conf-001")

        # Assert
        assert result is not None
        assert result.state == ConferenceState.ENDED
        assert result.summary == "完了"

    def test_remove(self):
        """会議を削除できる"""
        # Arrange
        store = ConferenceStore()
        store.add(
            ConferenceProjection(
                conference_id="conf-001",
                hive_id="hive-a",
                topic="会議1",
                participants=[],
                state=ConferenceState.ACTIVE,
            )
        )

        # Act
        store.remove("conf-001")
        result = store.get("conf-001")

        # Assert
        assert result is None

    def test_remove_nonexistent_no_error(self):
        """存在しない会議の削除はエラーにならない"""
        # Arrange
        store = ConferenceStore()

        # Act & Assert: エラーにならない
        store.remove("nonexistent")

    def test_clear(self):
        """全会議をクリアできる"""
        # Arrange
        store = ConferenceStore()
        store.add(
            ConferenceProjection(
                conference_id="conf-001",
                hive_id="hive-a",
                topic="会議1",
                participants=[],
                state=ConferenceState.ACTIVE,
            )
        )
        store.add(
            ConferenceProjection(
                conference_id="conf-002",
                hive_id="hive-a",
                topic="会議2",
                participants=[],
                state=ConferenceState.ACTIVE,
            )
        )

        # Act
        store.clear()
        result = store.list_all()

        # Assert
        assert len(result) == 0
