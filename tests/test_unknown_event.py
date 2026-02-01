"""UnknownEvent 前方互換のテスト

外部フィードバック対応: 未知のイベントタイプを例外ではなくUnknownEventとして読み込む。
"""

import pytest

from hiveforge.core.events import BaseEvent, UnknownEvent, parse_event


class TestUnknownEventClass:
    """UnknownEvent クラスのテスト"""

    def test_unknown_event_class_exists(self):
        """UnknownEventクラスが存在する"""
        # Assert
        assert UnknownEvent is not None
        assert issubclass(UnknownEvent, BaseEvent)

    def test_create_unknown_event(self):
        """UnknownEventを生成できる"""
        # Arrange & Act
        event = UnknownEvent(
            type="future.new_event_type",
            actor="system",
            payload={"key": "value"},
            original_data={"type": "future.new_event_type", "actor": "system"},
        )

        # Assert
        assert event.type == "future.new_event_type"
        assert event.payload["key"] == "value"
        assert event.original_data["type"] == "future.new_event_type"

    def test_unknown_event_preserves_original_data(self):
        """UnknownEventは元のデータを保持する"""
        # Arrange
        original = {
            "type": "some.unknown.type",
            "actor": "test",
            "payload": {"foo": "bar"},
            "extra_field": "should be preserved",
        }

        # Act
        event = UnknownEvent(
            type=original["type"],
            actor=original["actor"],
            payload=original["payload"],
            original_data=original,
        )

        # Assert
        assert event.original_data["extra_field"] == "should be preserved"


class TestParseEventForwardCompatibility:
    """parse_event の前方互換性テスト"""

    def test_parse_unknown_event_type_returns_unknown_event(self):
        """未知のイベントタイプはUnknownEventとして返す（例外にしない）"""
        # Arrange
        data = {
            "type": "future.unknown.event",
            "actor": "system",
            "payload": {"message": "from the future"},
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, UnknownEvent)
        assert event.type == "future.unknown.event"
        assert event.actor == "system"
        assert event.payload["message"] == "from the future"

    def test_parse_unknown_event_preserves_all_fields(self):
        """未知イベントのパース時に全フィールドを保持する"""
        # Arrange
        data = {
            "id": "01HXYZ123456",
            "type": "experimental.feature",
            "timestamp": "2026-02-01T12:00:00Z",
            "actor": "test-actor",
            "run_id": "run-001",
            "task_id": "task-001",
            "payload": {"key": "value"},
            "prev_hash": "abc123",
            "parents": ["parent-001"],
            "future_field": "should be in original_data",
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, UnknownEvent)
        assert event.original_data == data
        assert event.original_data["future_field"] == "should be in original_data"

    def test_parse_event_still_works_for_known_types(self):
        """既知のイベントタイプは従来通り正しくパースされる"""
        # Arrange
        from hiveforge.core.events import EventType, RunStartedEvent

        data = {
            "type": "run.started",
            "actor": "user",
            "payload": {"goal": "test"},
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, RunStartedEvent)
        assert event.type == EventType.RUN_STARTED

    def test_parse_unknown_event_from_json_string(self):
        """JSON文字列からも未知イベントをパースできる"""
        # Arrange
        import json

        data = {
            "type": "future.v10.event",
            "actor": "future-system",
            "payload": {},
        }
        json_str = json.dumps(data)

        # Act
        event = parse_event(json_str)

        # Assert
        assert isinstance(event, UnknownEvent)
        assert event.type == "future.v10.event"


class TestUnknownEventBehavior:
    """UnknownEventの振る舞いテスト"""

    def test_unknown_event_has_hash(self):
        """UnknownEventもハッシュを持つ"""
        # Arrange
        event = UnknownEvent(
            type="unknown.type",
            actor="system",
            payload={},
            original_data={},
        )

        # Act
        hash_value = event.hash

        # Assert
        assert hash_value is not None
        assert len(hash_value) == 64  # SHA-256

    def test_unknown_event_to_json(self):
        """UnknownEventをJSONにシリアライズできる"""
        # Arrange
        event = UnknownEvent(
            type="unknown.type",
            actor="system",
            payload={"key": "value"},
            original_data={"type": "unknown.type"},
        )

        # Act
        json_str = event.to_json()

        # Assert
        assert "unknown.type" in json_str
        assert "key" in json_str

    def test_unknown_event_supports_lineage(self):
        """UnknownEventもLineage（親イベント）を持てる"""
        # Arrange
        event = UnknownEvent(
            type="unknown.type",
            actor="system",
            payload={},
            original_data={},
            parents=["parent-event-001", "parent-event-002"],
        )

        # Assert
        assert len(event.parents) == 2
        assert "parent-event-001" in event.parents
