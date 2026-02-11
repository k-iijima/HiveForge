"""Queen Bee タスクコンテキスト共有のテスト

M4-2-a: エージェント間のコンテキスト共有。
先行タスクの成果物を後続タスクに渡す TaskContext のテスト。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from colonyforge.queen_bee.context import TaskContext, TaskResult

# =========================================================================
# TaskResult モデルのテスト
# =========================================================================


class TestTaskResult:
    """個別タスクの結果モデルテスト"""

    def test_create_success(self):
        """成功結果の作成"""
        # Act
        result = TaskResult(
            task_id="t1",
            goal="DB設計",
            status="completed",
            output="スキーマ定義完了",
        )

        # Assert
        assert result.task_id == "t1"
        assert result.status == "completed"
        assert result.output == "スキーマ定義完了"

    def test_create_failure(self):
        """失敗結果の作成"""
        # Act
        result = TaskResult(
            task_id="t2",
            goal="API実装",
            status="failed",
            error="接続エラー",
        )

        # Assert
        assert result.status == "failed"
        assert result.error == "接続エラー"

    def test_frozen(self):
        """TaskResultはイミュータブル"""
        # Arrange
        result = TaskResult(task_id="t1", goal="テスト", status="completed")

        # Act & Assert
        with pytest.raises(ValidationError):
            result.status = "failed"  # type: ignore

    def test_default_values(self):
        """デフォルト値が設定される"""
        # Act
        result = TaskResult(task_id="t1", goal="テスト", status="completed")

        # Assert
        assert result.output == ""
        assert result.error is None
        assert result.tool_calls_made == 0
        assert result.artifacts == {}


# =========================================================================
# TaskContext モデルのテスト
# =========================================================================


class TestTaskContext:
    """タスクコンテキスト共有テスト"""

    def test_create_empty(self):
        """空のコンテキストを作成"""
        # Act
        ctx = TaskContext(original_goal="ECサイト構築", run_id="run-1")

        # Assert
        assert ctx.original_goal == "ECサイト構築"
        assert ctx.run_id == "run-1"
        assert ctx.completed_tasks == {}
        assert ctx.failed_tasks == {}

    def test_add_completed_result(self):
        """完了タスク結果を追加"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        result = TaskResult(
            task_id="t1",
            goal="DB設計",
            status="completed",
            output="テーブル定義完了",
        )

        # Act
        ctx.add_result(result)

        # Assert
        assert "t1" in ctx.completed_tasks
        assert ctx.completed_tasks["t1"].output == "テーブル定義完了"

    def test_add_failed_result(self):
        """失敗タスク結果を追加"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        result = TaskResult(task_id="t2", goal="API実装", status="failed", error="エラー")

        # Act
        ctx.add_result(result)

        # Assert
        assert "t2" in ctx.failed_tasks
        assert ctx.failed_tasks["t2"].error == "エラー"

    def test_get_predecessor_results(self):
        """先行タスクの結果を取得"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(
            TaskResult(task_id="t1", goal="DB設計", status="completed", output="スキーマ完了")
        )
        ctx.add_result(
            TaskResult(task_id="t2", goal="API設計", status="completed", output="API仕様完了")
        )

        # Act: t3 の先行タスク（t1, t2）の結果を取得
        predecessors = ctx.get_predecessor_results(["t1", "t2"])

        # Assert
        assert len(predecessors) == 2
        assert predecessors["t1"].output == "スキーマ完了"
        assert predecessors["t2"].output == "API仕様完了"

    def test_get_predecessor_results_missing(self):
        """まだ完了していない先行タスクは空辞書"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")

        # Act
        predecessors = ctx.get_predecessor_results(["t1"])

        # Assert
        assert predecessors == {}

    def test_get_predecessor_results_partial(self):
        """一部のみ完了している場合は完了分のみ返す"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="DB設計", status="completed", output="完了"))

        # Act: t1は完了、t2は未完了
        predecessors = ctx.get_predecessor_results(["t1", "t2"])

        # Assert
        assert len(predecessors) == 1
        assert "t1" in predecessors
        assert "t2" not in predecessors

    def test_build_context_for_task(self):
        """タスク実行用のコンテキストdict を構築"""
        # Arrange
        ctx = TaskContext(original_goal="ECサイト構築", run_id="run-1")
        ctx.add_result(
            TaskResult(
                task_id="t1",
                goal="DB設計",
                status="completed",
                output="usersテーブル定義",
            )
        )

        # Act
        task_ctx = ctx.build_context_for_task(
            task_id="t2",
            goal="API実装",
            depends_on=["t1"],
        )

        # Assert
        assert task_ctx["original_goal"] == "ECサイト構築"
        assert task_ctx["current_task"]["task_id"] == "t2"
        assert task_ctx["current_task"]["goal"] == "API実装"
        assert len(task_ctx["predecessor_results"]) == 1
        assert task_ctx["predecessor_results"]["t1"]["output"] == "usersテーブル定義"

    def test_build_context_no_dependencies(self):
        """依存なしタスクのコンテキストにpredecessor_resultsが空"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")

        # Act
        task_ctx = ctx.build_context_for_task(task_id="t1", goal="独立タスク", depends_on=[])

        # Assert
        assert task_ctx["predecessor_results"] == {}

    def test_summary(self):
        """コンテキストのサマリーを取得"""
        # Arrange
        ctx = TaskContext(original_goal="テスト", run_id="run-1")
        ctx.add_result(TaskResult(task_id="t1", goal="タスク1", status="completed", output="OK"))
        ctx.add_result(TaskResult(task_id="t2", goal="タスク2", status="failed", error="NG"))

        # Act
        summary = ctx.summary()

        # Assert
        assert summary["completed_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["total_count"] == 2

    def test_add_artifact(self):
        """タスク結果にartifactsを含められる"""
        # Act
        result = TaskResult(
            task_id="t1",
            goal="ファイル生成",
            status="completed",
            output="生成完了",
            artifacts={"file_path": "/tmp/output.py", "lines": 42},
        )

        # Assert
        assert result.artifacts["file_path"] == "/tmp/output.py"
