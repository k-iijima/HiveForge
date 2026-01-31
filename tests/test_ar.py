"""Akashic Record ストレージのテスト"""

import pytest
from pathlib import Path

from hiveforge.core.ar import AkashicRecord
from hiveforge.core.events import (
    RunStartedEvent,
    TaskCreatedEvent,
    TaskCompletedEvent,
)


class TestAkashicRecord:
    """AkashicRecordのテスト"""

    def test_append_and_replay(self, temp_vault):
        """イベントの追記とリプレイ"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-001"

        # イベントを追記
        event1 = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        event2 = TaskCreatedEvent(
            run_id=run_id,
            task_id="task-001",
            payload={"title": "Task 1"},
        )

        ar.append(event1, run_id)
        ar.append(event2, run_id)

        # リプレイ
        events = list(ar.replay(run_id))
        assert len(events) == 2
        assert events[0].type == event1.type
        assert events[1].type == event2.type

    def test_event_chain_integrity(self, temp_vault):
        """イベントチェーンの整合性"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-002"

        # 複数イベントを追記
        for i in range(5):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i:03d}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # チェーンを検証
        valid, error = ar.verify_chain(run_id)
        assert valid is True
        assert error is None

    def test_list_runs(self, temp_vault):
        """Run一覧の取得"""
        ar = AkashicRecord(temp_vault)

        # 複数のRunを作成
        for i in range(3):
            run_id = f"run-{i:03d}"
            event = RunStartedEvent(run_id=run_id, payload={"goal": f"Goal {i}"})
            ar.append(event, run_id)

        runs = ar.list_runs()
        assert len(runs) == 3
        assert "run-000" in runs
        assert "run-001" in runs
        assert "run-002" in runs

    def test_count_events(self, temp_vault):
        """イベント数のカウント"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-count"

        # イベントを追記
        for i in range(10):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        count = ar.count_events(run_id)
        assert count == 10

    def test_get_last_event(self, temp_vault):
        """最後のイベント取得"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-last"

        # イベントを追記
        event1 = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        event2 = TaskCreatedEvent(
            run_id=run_id,
            task_id="task-001",
            payload={"title": "Last Task"},
        )

        ar.append(event1, run_id)
        ar.append(event2, run_id)

        last = ar.get_last_event(run_id)
        assert last is not None
        assert last.task_id == "task-001"

    def test_replay_empty_run(self, temp_vault):
        """存在しないRunのリプレイは空"""
        ar = AkashicRecord(temp_vault)
        events = list(ar.replay("nonexistent-run"))
        assert len(events) == 0

    def test_export_run(self, temp_vault):
        """Runのエクスポート"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-export"

        # イベントを追記
        for i in range(5):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # エクスポート
        export_path = temp_vault / "export.jsonl"
        count = ar.export_run(run_id, export_path)

        assert count == 5
        assert export_path.exists()

        # エクスポートファイルを検証
        with open(export_path) as f:
            lines = f.readlines()
        assert len(lines) == 5
