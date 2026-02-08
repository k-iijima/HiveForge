"""Queen Bee オーケストレータ — 並列タスク実行

TaskPlan の依存関係に基づき、層ごとにタスクを並列実行する。
先行タスクの結果は TaskContext 経由で後続タスクに渡される。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Protocol

from hiveforge.queen_bee.context import TaskContext, TaskResult
from hiveforge.queen_bee.planner import TaskPlan

logger = logging.getLogger(__name__)


class OrchestratorCallback(Protocol):
    """オーケストレータイベントコールバック

    ARイベント記録等の副作用を外部から注入する。
    """

    def on_task_skipped(self, task_id: str, goal: str, reason: str, run_id: str) -> None: ...

    def on_task_failed(self, task_id: str, goal: str, error: str, run_id: str) -> None: ...


class ColonyOrchestrator:
    """タスク依存関係に基づく並列実行オーケストレータ

    TaskPlan.execution_order() が返す層 (layer) ごとに
    asyncio.gather() でタスクを並列実行し、先行タスクの
    結果を TaskContext 経由で後続タスクに伝搬する。
    """

    async def execute_plan(
        self,
        plan: TaskPlan,
        execute_fn: Callable[..., Any],
        original_goal: str,
        run_id: str,
        callback: OrchestratorCallback | None = None,
    ) -> TaskContext:
        """タスクプランを依存関係順に実行する

        Args:
            plan: 実行するタスクプラン
            execute_fn: タスク実行関数
                signature: async (task_id, goal, context) -> dict
            original_goal: Colony の元の目標
            run_id: Run ID

        Returns:
            全タスクの結果を含む TaskContext
        """
        ctx = TaskContext(original_goal=original_goal, run_id=run_id)
        task_map = {t.task_id: t for t in plan.tasks}
        layers = plan.execution_order()

        for layer in layers:
            coros = []
            for task_id in layer:
                task = task_map[task_id]

                # 先行タスクが失敗していたらスキップ
                if self._has_failed_predecessor(task.depends_on, ctx):
                    reason = "先行タスク失敗によりスキップ"
                    ctx.add_result(
                        TaskResult(
                            task_id=task_id,
                            goal=task.goal,
                            status="skipped",
                            error=reason,
                        )
                    )
                    logger.error(
                        "タスク %s スキップ: %s (run_id=%s)",
                        task_id,
                        reason,
                        run_id,
                    )
                    if callback:
                        callback.on_task_skipped(task_id, task.goal, reason, run_id)
                    continue

                coros.append(
                    self._run_task(
                        task_id,
                        task.goal,
                        task.depends_on,
                        ctx,
                        execute_fn,
                        run_id,
                        callback,
                    )
                )

            if coros:
                await asyncio.gather(*coros)

        return ctx

    @staticmethod
    def _has_failed_predecessor(depends_on: list[str], ctx: TaskContext) -> bool:
        """先行タスクに失敗があるか判定する"""
        return any(dep in ctx.failed_tasks for dep in depends_on)

    @staticmethod
    async def _run_task(
        task_id: str,
        goal: str,
        depends_on: list[str],
        ctx: TaskContext,
        execute_fn: Callable[..., Any],
        run_id: str,
        callback: OrchestratorCallback | None,
    ) -> None:
        """1タスクを実行し、結果を TaskContext に記録する"""
        context = ctx.build_context_for_task(task_id, goal, depends_on) if depends_on else None

        try:
            result_data = await execute_fn(task_id, goal, context)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(
                "タスク %s で例外発生: %s (run_id=%s)",
                task_id,
                error_msg,
                ctx.run_id,
            )
            ctx.add_result(
                TaskResult(
                    task_id=task_id,
                    goal=goal,
                    status="failed",
                    error=str(exc),
                )
            )
            if callback:
                callback.on_task_failed(task_id, goal, error_msg, ctx.run_id)
            return

        status = result_data.get("status", "failed")
        if status == "completed":
            ctx.add_result(
                TaskResult(
                    task_id=task_id,
                    goal=goal,
                    status="completed",
                    output=result_data.get("result", ""),
                    tool_calls_made=result_data.get("tool_calls_made", 0),
                    artifacts=result_data.get("artifacts", {}),
                )
            )
        else:
            ctx.add_result(
                TaskResult(
                    task_id=task_id,
                    goal=goal,
                    status="failed",
                    error=result_data.get("reason", "不明なエラー"),
                )
            )
