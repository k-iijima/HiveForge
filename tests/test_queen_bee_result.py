"""Queen Bee Colony結果集約のテスト

M4-2-c: 実行結果の集約とQueen Beeへの報告。
TaskContext から ColonyResult を構築し、
Colony全体のステータスを判定する。
"""

from __future__ import annotations

import pytest

from hiveforge.queen_bee.context import TaskContext, TaskResult
from hiveforge.queen_bee.result import ColonyResult, ColonyResultBuilder, ColonyStatus

# =========================================================================
# ColonyResult モデルのテスト
# =========================================================================


class TestColonyStatus:
    """ColonyStatusのテスト"""

    def test_all_statuses_defined(self):
        """全ステータスが定義されている"""
        # Assert
        assert ColonyStatus.COMPLETED == "completed"
        assert ColonyStatus.PARTIAL_FAILURE == "partial_failure"
        assert ColonyStatus.FAILED == "failed"


class TestColonyResult:
    """ColonyResultモデルのテスト"""

    def test_frozen_model(self):
        """ColonyResultは不変"""
        # Arrange
        result = ColonyResult(
            colony_id="col-1",
            run_id="run-1",
            original_goal="テスト",
            status=ColonyStatus.COMPLETED,
            total_tasks=1,
            completed_count=1,
            failed_count=0,
            task_results=[],
        )

        # Act / Assert
        with pytest.raises(Exception):
            result.status = ColonyStatus.FAILED  # type: ignore[misc]

    def test_summary_text_generated(self):
        """ColonyResultBuilder経由でsummary_textが自動生成される"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="A", status="completed", output="ok"))
        ctx.add_result(TaskResult(task_id="t2", goal="B", status="completed", output="ok"))

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert "2/2" in result.summary_text
        assert "テスト" in result.summary_text


# =========================================================================
# ColonyResultBuilder のテスト
# =========================================================================


class TestColonyResultBuilder:
    """ColonyResultBuilderのテスト"""

    def test_all_tasks_completed(self):
        """全タスク成功 → COMPLETED"""
        # Arrange
        ctx = TaskContext(original_goal="UI構築", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="設計", status="completed", output="完了"))
        ctx.add_result(TaskResult(task_id="t2", goal="実装", status="completed", output="完了"))

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert result.status == ColonyStatus.COMPLETED
        assert result.total_tasks == 2
        assert result.completed_count == 2
        assert result.failed_count == 0

    def test_all_tasks_failed(self):
        """全タスク失敗 → FAILED"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="A", status="failed", error="エラー1"))
        ctx.add_result(TaskResult(task_id="t2", goal="B", status="failed", error="エラー2"))

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert result.status == ColonyStatus.FAILED
        assert result.total_tasks == 2
        assert result.completed_count == 0
        assert result.failed_count == 2

    def test_partial_failure(self):
        """一部成功・一部失敗 → PARTIAL_FAILURE"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="成功", status="completed", output="ok"))
        ctx.add_result(TaskResult(task_id="t2", goal="失敗", status="failed", error="err"))

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert result.status == ColonyStatus.PARTIAL_FAILURE
        assert result.completed_count == 1
        assert result.failed_count == 1

    def test_task_results_included(self):
        """個別タスク結果がtask_resultsに含まれる"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="設計", status="completed", output="設計完了"))

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert len(result.task_results) == 1
        assert result.task_results[0]["task_id"] == "t1"
        assert result.task_results[0]["output"] == "設計完了"

    def test_failed_task_results_included(self):
        """失敗タスクの結果もtask_resultsに含まれる"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="A", status="failed", error="接続エラー"))

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert len(result.task_results) == 1
        assert result.task_results[0]["status"] == "failed"
        assert result.task_results[0]["error"] == "接続エラー"

    def test_colony_id_and_run_id_preserved(self):
        """colony_id と run_id が保持される"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-abc")
        ctx.add_result(TaskResult(task_id="t1", goal="A", status="completed", output="ok"))

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-xyz")

        # Assert
        assert result.colony_id == "col-xyz"
        assert result.run_id == "run-abc"
        assert result.original_goal == "テスト"

    def test_empty_context_is_failed(self):
        """タスク結果が0件の場合は FAILED"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")

        # Act
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert result.status == ColonyStatus.FAILED
        assert result.total_tasks == 0

    def test_to_event_data_completed(self):
        """COMPLETED結果からイベントデータを生成"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="A", status="completed", output="ok"))
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Act
        event_data = result.to_event_data()

        # Assert
        assert event_data["colony_id"] == "col-1"
        assert event_data["status"] == "completed"
        assert event_data["total_tasks"] == 1
        assert event_data["completed_count"] == 1

    def test_to_event_data_failed(self):
        """FAILED結果からイベントデータを生成"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="A", status="failed", error="err"))
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Act
        event_data = result.to_event_data()

        # Assert
        assert event_data["status"] == "failed"
        assert "failed_tasks" in event_data

    def test_tool_calls_total(self):
        """ツール呼び出し総数が集計される"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(
            TaskResult(
                task_id="t1",
                goal="A",
                status="completed",
                output="ok",
                tool_calls_made=3,
            )
        )
        ctx.add_result(
            TaskResult(
                task_id="t2",
                goal="B",
                status="completed",
                output="ok",
                tool_calls_made=5,
            )
        )
        result = ColonyResultBuilder.build(ctx, colony_id="col-1")

        # Assert
        assert result.total_tool_calls == 8
