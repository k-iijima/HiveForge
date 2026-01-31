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


class TestAkashicRecordEdgeCases:
    """AkashicRecord のエッジケーステスト"""

    def test_append_without_run_id_raises_error(self, temp_vault):
        """run_idがない場合はエラーになる"""
        # Arrange: ARとrun_idがNoneのイベント
        ar = AkashicRecord(temp_vault)
        event = RunStartedEvent(run_id=None, payload={"goal": "Test"})

        # Act & Assert: run_idなしでappendするとエラー
        with pytest.raises(ValueError, match="run_id must be specified"):
            ar.append(event, run_id=None)

    def test_replay_with_since_filter(self, temp_vault):
        """since パラメータによる時刻フィルタリング"""
        from datetime import datetime, timezone, timedelta

        ar = AkashicRecord(temp_vault)
        run_id = "test-run-since"

        # 複数イベントを追記
        events_created = []
        for i in range(5):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            appended = ar.append(event, run_id)
            events_created.append(appended)

        # 中間のタイムスタンプ以降でフィルタ
        # 全イベントはほぼ同時刻なので、最初のイベントより前の時刻を使う
        since_time = events_created[0].timestamp - timedelta(seconds=1)
        filtered = list(ar.replay(run_id, since=since_time))
        assert len(filtered) == 5  # 全て取得

        # 未来の時刻を使うと何も取得されない
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        filtered = list(ar.replay(run_id, since=future_time))
        assert len(filtered) == 0

    def test_get_last_event_nonexistent_run(self, temp_vault):
        """存在しないRunの最終イベントはNone"""
        ar = AkashicRecord(temp_vault)
        result = ar.get_last_event("nonexistent-run")
        assert result is None

    def test_count_events_nonexistent_run(self, temp_vault):
        """存在しないRunのイベント数は0"""
        ar = AkashicRecord(temp_vault)
        count = ar.count_events("nonexistent-run")
        assert count == 0

    def test_verify_chain_detects_tampering(self, temp_vault):
        """改ざんされたチェーンを検出"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-tamper"

        # イベントを追記
        for i in range(3):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # ファイルを直接改ざん
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file, "r") as f:
            lines = f.readlines()

        # 2行目のprev_hashを改ざん
        import json

        data = json.loads(lines[1])
        data["prev_hash"] = "tampered_hash"
        lines[1] = json.dumps(data) + "\n"

        with open(events_file, "w") as f:
            f.writelines(lines)

        # 検証
        valid, error = ar.verify_chain(run_id)
        assert valid is False
        assert "Hash mismatch" in error

    def test_list_runs_excludes_directories_without_events(self, temp_vault):
        """events.jsonlがないディレクトリは除外される"""
        ar = AkashicRecord(temp_vault)

        # 正常なRunを作成
        event = RunStartedEvent(run_id="valid-run", payload={"goal": "Test"})
        ar.append(event, "valid-run")

        # events.jsonlがないディレクトリを作成
        empty_dir = temp_vault / "empty-run"
        empty_dir.mkdir()

        runs = ar.list_runs()
        assert "valid-run" in runs
        assert "empty-run" not in runs

    def test_replay_skips_empty_lines(self, temp_vault):
        """空行を含むファイルでもリプレイできる"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-empty-lines"

        # イベントを追記
        event = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        ar.append(event, run_id)

        # 空行を追加
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file, "a") as f:
            f.write("\n\n")  # 空行を追加

        # リプレイ
        events = list(ar.replay(run_id))
        assert len(events) == 1

    def test_get_last_event_with_empty_lines(self, temp_vault):
        """空行を含むファイルでも最終イベントを取得できる"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-last-empty"

        # イベントを追記
        event = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        ar.append(event, run_id)

        # 空行を追加
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file, "a") as f:
            f.write("\n\n")  # 末尾に空行

        # 最終イベント取得
        last = ar.get_last_event(run_id)
        assert last is not None

    def test_get_last_event_file_with_only_empty_lines(self, temp_vault):
        """空行のみのファイルではNoneを返す"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-only-empty"

        # ディレクトリと空行のみのファイルを作成
        run_dir = temp_vault / run_id
        run_dir.mkdir()
        events_file = run_dir / "events.jsonl"
        with open(events_file, "w") as f:
            f.write("\n\n\n")  # 空行のみ

        # 最終イベント取得
        last = ar.get_last_event(run_id)
        assert last is None

    def test_count_events_with_empty_lines(self, temp_vault):
        """空行を含むファイルでも正しくカウントする"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-count-empty"

        # イベントを追記
        for i in range(3):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # 空行を挿入
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file, "r") as f:
            content = f.read()
        # 途中に空行を挿入
        lines = content.split("\n")
        new_content = "\n\n".join(lines)  # 空行を挿入
        with open(events_file, "w") as f:
            f.write(new_content)

        # カウント
        count = ar.count_events(run_id)
        assert count == 3  # 空行は無視される
