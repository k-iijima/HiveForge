"""イベントモデルのテスト"""

import pytest
from datetime import datetime, timezone

from hiveforge.core.events import (
    BaseEvent,
    EventType,
    RunStartedEvent,
    TaskCreatedEvent,
    generate_event_id,
    compute_hash,
    parse_event,
)


class TestEventId:
    """イベントID生成のテスト"""

    def test_generate_event_id_returns_string(self):
        """IDが文字列で返される"""
        event_id = generate_event_id()
        assert isinstance(event_id, str)
        assert len(event_id) == 26  # ULID は26文字

    def test_generate_event_id_is_unique(self):
        """IDがユニーク"""
        ids = [generate_event_id() for _ in range(100)]
        assert len(ids) == len(set(ids))


class TestEventHash:
    """イベントハッシュのテスト"""

    def test_compute_hash_deterministic(self):
        """同じデータに対して同じハッシュ"""
        data = {"type": "test", "value": 123}
        hash1 = compute_hash(data)
        hash2 = compute_hash(data)
        assert hash1 == hash2

    def test_compute_hash_different_for_different_data(self):
        """異なるデータには異なるハッシュ"""
        hash1 = compute_hash({"type": "test", "value": 1})
        hash2 = compute_hash({"type": "test", "value": 2})
        assert hash1 != hash2

    def test_compute_hash_ignores_hash_field(self):
        """hashフィールドはハッシュ計算から除外"""
        data1 = {"type": "test", "value": 1}
        data2 = {"type": "test", "value": 1, "hash": "ignored"}
        assert compute_hash(data1) == compute_hash(data2)


class TestBaseEvent:
    """BaseEventのテスト"""

    def test_event_is_immutable(self):
        """イベントはイミュータブル"""
        event = RunStartedEvent(run_id="test-run", payload={"goal": "test"})
        with pytest.raises(Exception):  # ValidationError
            event.run_id = "changed"

    def test_event_has_auto_id(self):
        """イベントIDが自動生成される"""
        event = RunStartedEvent(run_id="test-run")
        assert event.id is not None
        assert len(event.id) == 26

    def test_event_has_auto_timestamp(self):
        """タイムスタンプが自動生成される"""
        event = RunStartedEvent(run_id="test-run")
        assert event.timestamp is not None
        assert event.timestamp.tzinfo == timezone.utc

    def test_event_hash_computed(self):
        """ハッシュが計算される"""
        event = RunStartedEvent(run_id="test-run")
        assert event.hash is not None
        assert len(event.hash) == 64  # SHA-256

    def test_event_serialization(self):
        """イベントのシリアライズ/デシリアライズ"""
        event = TaskCreatedEvent(
            run_id="test-run",
            task_id="test-task",
            payload={"title": "Test Task"},
        )

        json_str = event.to_json()
        restored = TaskCreatedEvent.from_json(json_str)

        assert restored.id == event.id
        assert restored.type == event.type
        assert restored.task_id == event.task_id
        assert restored.payload == event.payload


class TestParseEvent:
    """parse_event関数のテスト"""

    def test_parse_run_started_event(self):
        """RunStartedEventがパースできる"""
        data = {
            "type": "run.started",
            "run_id": "test-run",
            "payload": {"goal": "test"},
        }
        event = parse_event(data)
        assert isinstance(event, RunStartedEvent)
        assert event.run_id == "test-run"

    def test_parse_task_created_event(self):
        """TaskCreatedEventがパースできる"""
        data = {
            "type": "task.created",
            "run_id": "test-run",
            "task_id": "test-task",
            "payload": {"title": "Test"},
        }
        event = parse_event(data)
        assert isinstance(event, TaskCreatedEvent)
        assert event.task_id == "test-task"

    def test_parse_from_json_string(self):
        """JSON文字列からパースできる"""
        json_str = '{"type": "run.started", "run_id": "test", "payload": {}}'
        event = parse_event(json_str)
        assert isinstance(event, RunStartedEvent)
