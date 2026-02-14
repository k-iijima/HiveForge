"""Queen Bee タスク実行・LLM統合Mixin"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core import generate_event_id
from ..core.events import (
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
)

if TYPE_CHECKING:
    from ..core import AkashicRecord
    from ..core.config import LLMConfig
    from ..llm.client import LLMClient
    from ..llm.runner import AgentRunner
    from .server import ManagedWorker

logger = logging.getLogger(__name__)


class TaskRunnerMixin:
    """タスク実行・タスク分解・LLMクライアント初期化"""

    if TYPE_CHECKING:
        colony_id: str
        ar: AkashicRecord
        llm_config: LLMConfig | None
        _llm_client: LLMClient | None
        _agent_runner: AgentRunner | None

        def get_idle_workers(self) -> list[ManagedWorker]: ...

    async def _plan_tasks(self, goal: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        """LLMを使ってタスクを分解

        Returns:
            タスク辞書リスト。各辞書は task_id, goal, depends_on を含む。
        """
        from colonyforge.queen_bee.planner import TaskPlanner

        client = await self._get_llm_client()
        planner = TaskPlanner(client)
        plan = await planner.plan(goal, context)
        return [
            {
                "task_id": task.task_id,
                "goal": task.goal,
                "depends_on": list(task.depends_on),
            }
            for task in plan.tasks
        ]

    async def _execute_task(
        self,
        task_id: str,
        run_id: str,
        goal: str,
        context: dict[str, Any],
        worker: Any | None = None,
    ) -> dict[str, Any]:
        """タスクをWorkerで実行"""
        # Workerを選択
        if not worker:
            idle_workers = self.get_idle_workers()
            if not idle_workers:
                return {
                    "status": "error",
                    "task_id": task_id,
                    "error": "No available workers",
                }
            worker = idle_workers[0]

        worker.current_task_id = task_id

        # TaskCreatedイベントを発行
        task_event = TaskCreatedEvent(
            id=generate_event_id(),
            run_id=run_id,
            actor=f"queen-{self.colony_id}",
            payload={
                "task_id": task_id,
                "goal": goal,
                "assigned_worker": worker.worker_id,
            },
        )
        self.ar.append(task_event, run_id)

        # TaskAssignedイベントを発行
        assign_event = TaskAssignedEvent(
            id=generate_event_id(),
            run_id=run_id,
            actor=f"queen-{self.colony_id}",
            payload={
                "task_id": task_id,
                "worker_id": worker.worker_id,
            },
        )
        self.ar.append(assign_event, run_id)

        # Worker BeeでLLM実行
        try:
            result = await worker.server.execute_task_with_llm(
                {
                    "task_id": task_id,
                    "run_id": run_id,
                    "goal": goal,
                    "context": context,
                }
            )

            worker.current_task_id = None

            if result.get("status") == "completed":
                # TaskCompletedイベントを発行
                completed_event = TaskCompletedEvent(
                    id=generate_event_id(),
                    run_id=run_id,
                    actor=f"queen-{self.colony_id}",
                    payload={
                        "task_id": task_id,
                        "worker_id": worker.worker_id,
                        "result": result.get("result", ""),
                    },
                )
                self.ar.append(completed_event, run_id)

                return {
                    "status": "completed",
                    "task_id": task_id,
                    "worker_id": worker.worker_id,
                    "result": result.get("result", ""),
                    "llm_output": result.get("llm_output", ""),
                    "tool_calls_made": result.get("tool_calls_made", 0),
                }
            else:
                # TaskFailedイベントを発行
                failed_event = TaskFailedEvent(
                    id=generate_event_id(),
                    run_id=run_id,
                    actor=f"queen-{self.colony_id}",
                    payload={
                        "task_id": task_id,
                        "worker_id": worker.worker_id,
                        "reason": result.get("reason", result.get("llm_error", "Unknown")),
                    },
                )
                self.ar.append(failed_event, run_id)

                return {
                    "status": "failed",
                    "task_id": task_id,
                    "worker_id": worker.worker_id,
                    "error": result.get("reason", result.get("llm_error", "Unknown")),
                }

        except Exception as e:
            worker.current_task_id = None
            from .pipeline import TaskExecutionError

            raise TaskExecutionError(
                task_id=task_id,
                worker_id=worker.worker_id,
                cause=e,
            ) from e

    async def _get_llm_client(self) -> Any:
        """LLMクライアントを取得（遅延初期化）"""
        if self._llm_client is None:
            from ..llm.client import LLMClient

            self._llm_client = LLMClient(config=self.llm_config)
        return self._llm_client

    async def _get_agent_runner(self) -> Any:
        """AgentRunnerを取得（遅延初期化）"""
        if self._agent_runner is None:
            from ..core.activity_bus import AgentInfo, AgentRole
            from ..llm.runner import AgentRunner

            client = await self._get_llm_client()
            agent_info = AgentInfo(
                agent_id=f"queen-{self.colony_id}",
                role=AgentRole.QUEEN_BEE,
                hive_id="0",
                colony_id=self.colony_id,
            )
            self._agent_runner = AgentRunner(
                client,
                agent_type="queen_bee",
                vault_path=str(self.ar.vault_path),
                colony_id=self.colony_id,
                agent_info=agent_info,
            )

        return self._agent_runner
