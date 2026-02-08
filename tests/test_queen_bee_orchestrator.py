"""Queen Bee オーケストレータのテスト

M4-2-b: 複数Worker Beeの並列実行と結果集約。
ColonyOrchestrator がタスク依存関係を解析し、
層ごとにWorkerを並列実行するテスト。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hiveforge.queen_bee.context import TaskContext
from hiveforge.queen_bee.orchestrator import ColonyOrchestrator
from hiveforge.queen_bee.planner import PlannedTask, TaskPlan

# =========================================================================
# ColonyOrchestrator の並列実行テスト
# =========================================================================


class TestColonyOrchestrator:
    """ColonyOrchestratorのテスト"""

    @pytest.fixture
    def mock_execute(self):
        """タスク実行関数のモック"""

        async def _execute(task_id: str, goal: str, context: dict | None) -> dict:
            return {
                "status": "completed",
                "task_id": task_id,
                "result": f"{goal}完了",
                "tool_calls_made": 1,
            }

        return AsyncMock(side_effect=_execute)

    @pytest.fixture
    def orchestrator(self):
        return ColonyOrchestrator()

    @pytest.mark.asyncio
    async def test_single_task(self, orchestrator, mock_execute):
        """単一タスクの実行"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト実行")])

        # Act
        ctx = await orchestrator.execute_plan(
            plan=plan,
            execute_fn=mock_execute,
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert
        assert len(ctx.completed_tasks) == 1
        assert "t1" in ctx.completed_tasks
        mock_execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_independent_tasks_parallel(self, orchestrator, mock_execute):
        """独立タスクが並列実行される"""
        # Arrange: 依存関係なし→並列実行
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="UI設計"),
            ]
        )

        # Act
        ctx = await orchestrator.execute_plan(
            plan=plan,
            execute_fn=mock_execute,
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert: 両方完了
        assert len(ctx.completed_tasks) == 2
        assert mock_execute.await_count == 2

    @pytest.mark.asyncio
    async def test_sequential_tasks_order(self, orchestrator, mock_execute):
        """依存タスクが正しい順序で実行される"""
        # Arrange
        execution_order = []

        async def _ordered_execute(task_id, goal, context):
            execution_order.append(task_id)
            return {"status": "completed", "task_id": task_id, "result": "ok"}

        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装", depends_on=["t1"]),
                PlannedTask(task_id="t3", goal="テスト", depends_on=["t2"]),
            ]
        )

        # Act
        await orchestrator.execute_plan(
            plan=plan,
            execute_fn=AsyncMock(side_effect=_ordered_execute),
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert: t1→t2→t3 の順序
        assert execution_order == ["t1", "t2", "t3"]

    @pytest.mark.asyncio
    async def test_diamond_dependency(self, orchestrator, mock_execute):
        """ダイヤモンド依存: t1→(t2,t3)→t4"""
        # Arrange
        execution_order = []

        async def _ordered_execute(task_id, goal, context):
            execution_order.append(task_id)
            return {"status": "completed", "task_id": task_id, "result": "ok"}

        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="基盤"),
                PlannedTask(task_id="t2", goal="機能A", depends_on=["t1"]),
                PlannedTask(task_id="t3", goal="機能B", depends_on=["t1"]),
                PlannedTask(task_id="t4", goal="結合", depends_on=["t2", "t3"]),
            ]
        )

        # Act
        ctx = await orchestrator.execute_plan(
            plan=plan,
            execute_fn=AsyncMock(side_effect=_ordered_execute),
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert: t1が最初、t4が最後、t2/t3はt1の後
        assert execution_order[0] == "t1"
        assert execution_order[-1] == "t4"
        assert set(execution_order[1:3]) == {"t2", "t3"}
        assert len(ctx.completed_tasks) == 4

    @pytest.mark.asyncio
    async def test_context_passed_to_dependent_task(self, orchestrator):
        """先行タスクの結果が後続タスクのcontextに渡される"""
        # Arrange
        received_contexts = {}

        async def _capture_execute(task_id, goal, context):
            received_contexts[task_id] = context
            return {"status": "completed", "task_id": task_id, "result": f"{goal}完了"}

        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装", depends_on=["t1"]),
            ]
        )

        # Act
        await orchestrator.execute_plan(
            plan=plan,
            execute_fn=AsyncMock(side_effect=_capture_execute),
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert: t2のcontextにt1の結果が含まれる
        t2_ctx = received_contexts["t2"]
        assert "predecessor_results" in t2_ctx
        assert "t1" in t2_ctx["predecessor_results"]
        assert t2_ctx["predecessor_results"]["t1"]["output"] == "DB設計完了"

    @pytest.mark.asyncio
    async def test_task_failure_does_not_block_independent(self, orchestrator):
        """1つのタスクが失敗しても、独立タスクは実行される"""

        # Arrange
        async def _failing_execute(task_id, goal, context):
            if task_id == "t1":
                return {"status": "failed", "task_id": task_id, "reason": "エラー"}
            return {"status": "completed", "task_id": task_id, "result": "ok"}

        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="失敗タスク"),
                PlannedTask(task_id="t2", goal="成功タスク"),
            ]
        )

        # Act
        ctx = await orchestrator.execute_plan(
            plan=plan,
            execute_fn=AsyncMock(side_effect=_failing_execute),
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert: t1失敗、t2成功
        assert len(ctx.failed_tasks) == 1
        assert len(ctx.completed_tasks) == 1

    @pytest.mark.asyncio
    async def test_dependent_task_skipped_on_predecessor_failure(self, orchestrator):
        """先行タスクが失敗した場合、依存タスクはスキップされる"""

        # Arrange
        async def _failing_execute(task_id, goal, context):
            if task_id == "t1":
                return {"status": "failed", "task_id": task_id, "reason": "エラー"}
            return {"status": "completed", "task_id": task_id, "result": "ok"}

        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="基盤（失敗）"),
                PlannedTask(task_id="t2", goal="依存タスク", depends_on=["t1"]),
            ]
        )

        # Act
        ctx = await orchestrator.execute_plan(
            plan=plan,
            execute_fn=AsyncMock(side_effect=_failing_execute),
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert: t1失敗、t2はスキップ（failed扱い）
        assert "t1" in ctx.failed_tasks
        assert "t2" in ctx.failed_tasks
        assert "スキップ" in ctx.failed_tasks["t2"].error

    @pytest.mark.asyncio
    async def test_returns_task_context(self, orchestrator, mock_execute):
        """execute_planがTaskContextを返す"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト")])

        # Act
        ctx = await orchestrator.execute_plan(
            plan=plan,
            execute_fn=mock_execute,
            original_goal="テスト目標",
            run_id="run-1",
        )

        # Assert
        assert isinstance(ctx, TaskContext)
        assert ctx.original_goal == "テスト目標"
        assert ctx.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_exception_in_execute_treated_as_failure(self, orchestrator):
        """execute関数で例外が発生した場合はfailed扱い"""

        # Arrange
        async def _error_execute(task_id, goal, context):
            raise RuntimeError("接続エラー")

        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト")])

        # Act
        ctx = await orchestrator.execute_plan(
            plan=plan,
            execute_fn=AsyncMock(side_effect=_error_execute),
            original_goal="テスト",
            run_id="run-1",
        )

        # Assert
        assert "t1" in ctx.failed_tasks
        assert "接続エラー" in ctx.failed_tasks["t1"].error
