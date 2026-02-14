"""Queen Bee 目標実行Mixin"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core import generate_event_id
from ..core.events import (
    ColonyStartedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
)

if TYPE_CHECKING:
    from ..core import AkashicRecord
    from .server import ManagedWorker

logger = logging.getLogger(__name__)


class ExecutionMixin:
    """目標実行: handle_execute_goal, _execute_direct, 簡易ハンドラ"""

    if TYPE_CHECKING:
        colony_id: str
        ar: AkashicRecord
        use_pipeline: bool
        _current_run_id: str | None
        _workers: dict[str, ManagedWorker]

        def add_worker(self, worker_id: str) -> ManagedWorker: ...
        def get_worker(self, worker_id: str) -> ManagedWorker | None: ...
        def get_idle_workers(self) -> list[ManagedWorker]: ...
        async def _plan_tasks(self, goal: str, context: dict[str, Any]) -> list[dict[str, Any]]: ...
        async def _execute_task(
            self,
            task_id: str,
            run_id: str,
            goal: str,
            context: dict[str, Any],
            worker: Any | None = None,
        ) -> dict[str, Any]: ...
        async def _execute_with_pipeline(
            self,
            run_id: str,
            goal: str,
            context: dict[str, Any],
            approval_decision: Any | None = None,
        ) -> dict[str, Any]: ...

    async def handle_execute_goal(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """目標実行ハンドラ

        目標をタスクに分解し、Worker Beeで実行する。
        RunStarted/RunCompleted/RunFailedイベントを発行して追跡可能にする。

        use_pipeline=True の場合、ExecutionPipeline を通じて
        Guard Bee検証 + 承認ゲートを経由して実行する。
        """
        run_id = arguments.get("run_id", generate_event_id())
        goal = arguments.get("goal", "")
        context = arguments.get("context", {})

        self._current_run_id = run_id

        # Workerがいなければ1つ作成
        if not self._workers:
            self.add_worker(f"worker-{self.colony_id}-1")

        # RunStartedイベントを発行
        run_started = RunStartedEvent(
            id=generate_event_id(),
            run_id=run_id,
            actor=f"queen-{self.colony_id}",
            payload={
                "colony_id": self.colony_id,
                "goal": goal,
            },
        )
        self.ar.append(run_started, run_id)

        # ColonyStartedイベントを発行（初回のみ）
        colony_started = ColonyStartedEvent(
            id=generate_event_id(),
            run_id=run_id,
            actor=f"queen-{self.colony_id}",
            payload={
                "colony_id": self.colony_id,
            },
        )
        self.ar.append(colony_started, run_id)

        if self.use_pipeline:
            return await self._execute_with_pipeline(run_id, goal, context)
        else:
            return await self._execute_direct(run_id, goal, context)

    async def _execute_direct(
        self, run_id: str, goal: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """直接実行パス（Pipeline なし）

        ColonyOrchestrator を使い、依存関係に基づく並列実行と
        TaskContext によるコンテキスト伝搬を行う。
        """
        from .orchestrator import ColonyOrchestrator
        from .planner import PlannedTask, TaskPlan
        from .result import ColonyResultBuilder

        try:
            # LLMでタスク分解
            tasks_raw = await self._plan_tasks(goal, context)

            if not tasks_raw:
                tasks_raw = [{"task_id": str(generate_event_id()), "goal": goal, "depends_on": []}]

            # TaskPlan を構築（depends_on を保持）
            planned_tasks = [
                PlannedTask(
                    task_id=t.get("task_id", str(generate_event_id())),
                    goal=t["goal"],
                    depends_on=t.get("depends_on", []),
                )
                for t in tasks_raw
            ]
            plan = TaskPlan(tasks=planned_tasks, reasoning=f"Goal: {goal}")

            # ColonyOrchestrator で依存関係順に並列実行
            orchestrator = ColonyOrchestrator()

            async def execute_fn(task_id: str, task_goal: str, context_data: Any) -> dict[str, Any]:
                return await self._execute_task(
                    task_id=task_id,
                    run_id=run_id,
                    goal=task_goal,
                    context=context_data or context,
                )

            task_ctx = await orchestrator.execute_plan(
                plan=plan,
                execute_fn=execute_fn,
                original_goal=goal,
                run_id=run_id,
            )

            # TaskContext → ColonyResult に変換
            colony_result = ColonyResultBuilder.build(task_ctx, self.colony_id)

            # Run完了/失敗イベントを記録
            if colony_result.failed_count == 0:
                run_completed = RunCompletedEvent(
                    id=generate_event_id(),
                    run_id=run_id,
                    actor=f"queen-{self.colony_id}",
                    payload={
                        "colony_id": self.colony_id,
                        "goal": goal,
                        "tasks_completed": colony_result.completed_count,
                        "tasks_total": colony_result.total_tasks,
                    },
                )
                self.ar.append(run_completed, run_id)
            else:
                run_failed = RunFailedEvent(
                    id=generate_event_id(),
                    run_id=run_id,
                    actor=f"queen-{self.colony_id}",
                    payload={
                        "colony_id": self.colony_id,
                        "goal": goal,
                        "tasks_completed": colony_result.completed_count,
                        "tasks_total": colony_result.total_tasks,
                        "reason": "Some tasks failed",
                    },
                )
                self.ar.append(run_failed, run_id)

            return {
                "status": "completed" if colony_result.failed_count == 0 else "partial",
                "run_id": run_id,
                "goal": goal,
                "tasks_total": colony_result.total_tasks,
                "tasks_completed": colony_result.completed_count,
                "results": colony_result.task_results,
            }

        except Exception as e:
            logger.exception(f"目標実行エラー: {e}")

            run_failed = RunFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor=f"queen-{self.colony_id}",
                payload={
                    "colony_id": self.colony_id,
                    "goal": goal,
                    "reason": str(e),
                },
            )
            self.ar.append(run_failed, run_id)

            return {
                "status": "error",
                "run_id": run_id,
                "goal": goal,
                "error": str(e),
            }

    async def handle_plan_tasks(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """タスク分解ハンドラ"""
        goal = arguments.get("goal", "")
        context = arguments.get("context", {})

        tasks = await self._plan_tasks(goal, context)

        return {
            "status": "success",
            "goal": goal,
            "tasks": tasks,
        }

    async def handle_assign_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """タスク割り当てハンドラ"""
        task_id = arguments.get("task_id", "")
        run_id = arguments.get("run_id", "")
        goal = arguments.get("goal", "")
        worker_id = arguments.get("worker_id")
        context = arguments.get("context", {})

        # Workerを選択
        if worker_id:
            worker = self.get_worker(worker_id)
            if not worker:
                return {"error": f"Worker {worker_id} not found"}
        else:
            idle_workers = self.get_idle_workers()
            if not idle_workers:
                return {"error": "No available workers"}
            worker = idle_workers[0]

        # タスクを実行
        result = await self._execute_task(task_id, run_id, goal, context, worker)
        return result
