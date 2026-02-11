"""UnknownEvent 前方互換のテスト

外部フィードバック対応: 未知のイベントタイプを例外ではなくUnknownEventとして読み込む。
"""

from colonyforge.core.events import BaseEvent, UnknownEvent, parse_event


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
        from colonyforge.core.events import EventType, RunStartedEvent

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


class TestUnknownEventSafeguards:
    """UnknownEvent のセーフガードテスト

    外部入力由来の不正・巨大payloadに対する防御を検証する。
    """

    def test_original_data_size_limit_truncates_large_data(self):
        """巨大なoriginal_dataはサイズ上限で切り詰められる

        1MBを超えるoriginal_dataはメタデータのみ保持し、
        メモリ・ログ肥大化を防止する。
        """
        from colonyforge.core.events import MAX_ORIGINAL_DATA_SIZE

        # Arrange: 1MBを超える大きなデータ
        large_data = {
            "type": "malicious.large_event",
            "payload": "x" * (MAX_ORIGINAL_DATA_SIZE + 1000),
        }

        # Act
        event = UnknownEvent(
            type="malicious.large_event",
            actor="external",
            payload={},
            original_data=large_data,
        )

        # Assert: 切り詰められている
        assert event.original_data.get("_truncated") is True
        assert event.original_data["_original_size"] > MAX_ORIGINAL_DATA_SIZE
        assert event.original_data["_max_size"] == MAX_ORIGINAL_DATA_SIZE
        assert event.original_data["type"] == "malicious.large_event"
        # 元の大きなデータは保持されていない
        assert "payload" not in event.original_data or event.original_data.get("payload") is None

    def test_normal_size_original_data_preserved(self):
        """通常サイズのoriginal_dataはそのまま保持される"""
        # Arrange
        normal_data = {
            "type": "future.event",
            "actor": "system",
            "payload": {"key": "value"},
            "extra": "preserved",
        }

        # Act
        event = UnknownEvent(
            type="future.event",
            actor="system",
            payload={},
            original_data=normal_data,
        )

        # Assert: 全データがそのまま保持
        assert event.original_data == normal_data
        assert "_truncated" not in event.original_data

    def test_empty_original_data_accepted(self):
        """空のoriginal_dataは正常に受理される"""
        # Act
        event = UnknownEvent(
            type="empty.event",
            actor="system",
            payload={},
            original_data={},
        )

        # Assert
        assert event.original_data == {}

    def test_parse_event_with_oversized_unknown_data(self):
        """parse_eventが巨大な未知イベントを安全に処理する"""
        from colonyforge.core.events import MAX_ORIGINAL_DATA_SIZE

        # Arrange: 1MB超の未知イベントデータ
        oversized_data = {
            "type": "future.mega_event",
            "actor": "external",
            "payload": {"huge": "a" * (MAX_ORIGINAL_DATA_SIZE + 500)},
        }

        # Act
        event = parse_event(oversized_data)

        # Assert: UnknownEventとして安全に処理
        assert isinstance(event, UnknownEvent)
        assert event.original_data.get("_truncated") is True
