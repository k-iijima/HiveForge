"""Queen Bee Pipeline実行Mixin"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core import generate_event_id
from ..core.events import (
    RunCompletedEvent,
    RunFailedEvent,
)

if TYPE_CHECKING:
    from ..core import AkashicRecord
    from ..core.models.action_class import TrustLevel

logger = logging.getLogger(__name__)


class PipelineExecutionMixin:
    """Pipeline経由の実行 + 承認再開"""

    if TYPE_CHECKING:
        colony_id: str
        ar: AkashicRecord
        trust_level: TrustLevel
        _pending_approvals: dict[str, dict[str, Any]]

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
    ) -> dict[str, Any]:
        """ExecutionPipeline 経由でタスクを実行する

        Guard Bee検証 → 承認ゲート → ColonyOrchestrator並列実行
        """
        from .pipeline import ApprovalRequiredError, ExecutionPipeline, PipelineError
        from .planner import PlannedTask, TaskPlan

        try:
            # LLMでタスク分解
            tasks_raw = await self._plan_tasks(goal, context)
            if not tasks_raw:
                tasks_raw = [{"task_id": str(generate_event_id()), "goal": goal}]

            # TaskPlan を構築（depends_on を復元）
            planned_tasks = [
                PlannedTask(
                    task_id=t.get("task_id", str(generate_event_id())),
                    goal=t["goal"],
                    depends_on=t.get("depends_on", []),
                )
                for t in tasks_raw
            ]
            plan = TaskPlan(tasks=planned_tasks, reasoning=f"Goal: {goal}")

            # ExecutionPipeline を実行
            pipeline = ExecutionPipeline(ar=self.ar, trust_level=self.trust_level)

            async def execute_fn(task_id: str, goal: str, context_data: Any) -> dict[str, Any]:
                """Pipeline から呼ばれるタスク実行関数"""
                return await self._execute_task(
                    task_id=task_id,
                    run_id=run_id,
                    goal=goal,
                    context=context_data or context,
                )

            colony_result = await pipeline.run(
                plan=plan,
                execute_fn=execute_fn,
                colony_id=self.colony_id,
                run_id=run_id,
                original_goal=goal,
                approval_decision=approval_decision,
            )

            # RunCompleted/RunFailed を記録
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

        except ApprovalRequiredError as e:
            # 承認待ち — コンテキストを保存して approval_required を返す
            request_id = str(generate_event_id())
            self._pending_approvals[request_id] = {
                "run_id": run_id,
                "goal": goal,
                "context": context,
                "approval_request": e.approval_request,
            }
            logger.info(f"承認待ち: request_id={request_id}, goal={goal}")

            return {
                "status": "approval_required",
                "run_id": run_id,
                "goal": goal,
                "request_id": request_id,
                "action_class": e.approval_request.action_class.value,
                "task_count": e.approval_request.task_count,
            }

        except PipelineError as e:
            logger.exception(f"パイプラインエラー: {e}")

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

        except Exception as e:
            # MCP境界層: 例外型情報を保持してRunFailedEventに記録
            exc_type = type(e).__name__
            logger.exception("目標実行エラー (%s): %s", exc_type, e)

            run_failed = RunFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor=f"queen-{self.colony_id}",
                payload={
                    "colony_id": self.colony_id,
                    "goal": goal,
                    "reason": str(e),
                    "exception_type": exc_type,
                },
            )
            self.ar.append(run_failed, run_id)

            return {
                "status": "error",
                "run_id": run_id,
                "goal": goal,
                "error": str(e),
                "exception_type": exc_type,
            }

    async def resume_with_approval(
        self,
        request_id: str,
        approved: bool,
        reason: str = "",
    ) -> dict[str, Any]:
        """承認/拒否を受けて実行を再開する

        Args:
            request_id: 承認リクエストID
            approved: 承認されたか
            reason: 理由

        Returns:
            実行結果
        """
        from .approval import ApprovalDecision

        pending = self._pending_approvals.pop(request_id, None)
        if not pending:
            return {
                "status": "error",
                "error": f"Unknown request_id: {request_id}",
            }

        if not approved:
            return {
                "status": "rejected",
                "run_id": pending["run_id"],
                "reason": reason,
            }

        # 承認付きで再実行
        decision = ApprovalDecision(approved=True, reason=reason)
        return await self._execute_with_pipeline(
            run_id=pending["run_id"],
            goal=pending["goal"],
            context=pending["context"],
            approval_decision=decision,
        )
