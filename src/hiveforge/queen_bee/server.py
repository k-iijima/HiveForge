"""Queen Bee MCPサーバー

Colonyを統括し、タスクを分解してWorker Beeに割り当てる。
LLMを使用してタスク分解と進捗管理を行う。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.config import LLMConfig
from ..core.events import (
    ColonyStartedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
)
from ..core.models.action_class import TrustLevel
from ..worker_bee.server import WorkerBeeMCPServer, WorkerState

logger = logging.getLogger(__name__)


@dataclass
class ManagedWorker:
    """管理対象のWorker Bee"""

    worker_id: str
    server: WorkerBeeMCPServer
    current_task_id: str | None = None


@dataclass
class QueenBeeMCPServer:
    """Queen Bee MCPサーバー

    Colonyを統括し、タスクを分解してWorker Beeに割り当てる。
    MCPプロトコルでBeekeeperと通信する。
    LLMを使用してタスク分解を行う。
    """

    colony_id: str
    ar: AkashicRecord
    llm_config: LLMConfig | None = None  # エージェント別LLM設定
    use_pipeline: bool = False  # ExecutionPipeline を使用するか
    trust_level: TrustLevel = TrustLevel.PROPOSE_CONFIRM  # 承認レベル

    def __post_init__(self) -> None:
        """初期化"""
        self._llm_client = None
        self._agent_runner = None
        self._workers: dict[str, ManagedWorker] = {}
        self._pending_tasks: list[dict[str, Any]] = []
        self._current_run_id: str | None = None
        self._pending_approvals: dict[str, dict[str, Any]] = {}  # request_id -> approval context

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """MCPツール定義を取得

        Beekeeper/ユーザーがQueen Beeに対して実行できるツール。
        """
        return [
            {
                "name": "execute_goal",
                "description": "目標を受け取り、タスクに分解してWorker Beeで実行する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string", "description": "Run ID"},
                        "goal": {"type": "string", "description": "達成する目標（自然言語）"},
                        "context": {
                            "type": "object",
                            "description": "コンテキスト情報",
                            "properties": {
                                "working_directory": {"type": "string"},
                            },
                        },
                    },
                    "required": ["run_id", "goal"],
                },
            },
            {
                "name": "plan_tasks",
                "description": "目標をタスクに分解する（実行はしない）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "分解する目標"},
                        "context": {"type": "object", "description": "コンテキスト"},
                    },
                    "required": ["goal"],
                },
            },
            {
                "name": "assign_task",
                "description": "タスクをWorker Beeに割り当てる",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "タスクID"},
                        "run_id": {"type": "string", "description": "Run ID"},
                        "goal": {"type": "string", "description": "タスクの目標"},
                        "worker_id": {
                            "type": "string",
                            "description": "割り当てるWorker ID（省略時は自動選択）",
                        },
                    },
                    "required": ["task_id", "run_id", "goal"],
                },
            },
            {
                "name": "get_colony_status",
                "description": "Colonyの状態を取得",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "add_worker",
                "description": "Worker BeeをColonyに追加",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "worker_id": {"type": "string", "description": "Worker ID"},
                    },
                    "required": ["worker_id"],
                },
            },
            {
                "name": "remove_worker",
                "description": "Worker BeeをColonyから削除",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "worker_id": {"type": "string", "description": "Worker ID"},
                    },
                    "required": ["worker_id"],
                },
            },
        ]

    # -------------------------------------------------------------------------
    # Worker管理
    # -------------------------------------------------------------------------

    def add_worker(self, worker_id: str) -> ManagedWorker:
        """Worker BeeをColonyに追加"""
        if worker_id in self._workers:
            return self._workers[worker_id]

        server = WorkerBeeMCPServer(
            worker_id=worker_id,
            ar=self.ar,
            llm_config=self.llm_config,
        )
        managed = ManagedWorker(worker_id=worker_id, server=server)
        self._workers[worker_id] = managed
        logger.info(f"Worker {worker_id} をColony {self.colony_id} に追加")
        return managed

    def remove_worker(self, worker_id: str) -> bool:
        """Worker BeeをColonyから削除"""
        if worker_id not in self._workers:
            return False

        del self._workers[worker_id]
        logger.info(f"Worker {worker_id} をColony {self.colony_id} から削除")
        return True

    def get_idle_workers(self) -> list[ManagedWorker]:
        """利用可能なWorkerを取得"""
        return [w for w in self._workers.values() if w.server.state == WorkerState.IDLE]

    def get_worker(self, worker_id: str) -> ManagedWorker | None:
        """Workerを取得"""
        return self._workers.get(worker_id)

    # -------------------------------------------------------------------------
    # ハンドラ実装
    # -------------------------------------------------------------------------

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

    async def handle_get_colony_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Colony状態取得ハンドラ"""
        workers_status = []
        for w in self._workers.values():
            workers_status.append(
                {
                    "worker_id": w.worker_id,
                    "state": w.server.state.value,
                    "current_task_id": w.current_task_id,
                }
            )

        return {
            "status": "success",
            "colony_id": self.colony_id,
            "current_run_id": self._current_run_id,
            "workers": workers_status,
            "worker_count": len(self._workers),
            "idle_count": len(self.get_idle_workers()),
            "pending_tasks": len(self._pending_tasks),
        }

    async def handle_add_worker(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Worker追加ハンドラ"""
        worker_id = arguments.get("worker_id", "")
        worker = self.add_worker(worker_id)
        return {
            "status": "added",
            "worker_id": worker.worker_id,
            "colony_id": self.colony_id,
        }

    async def handle_remove_worker(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Worker削除ハンドラ"""
        worker_id = arguments.get("worker_id", "")
        if self.remove_worker(worker_id):
            return {
                "status": "removed",
                "worker_id": worker_id,
            }
        else:
            return {"error": f"Worker {worker_id} not found"}

    # -------------------------------------------------------------------------
    # 内部メソッド
    # -------------------------------------------------------------------------

    async def _plan_tasks(self, goal: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        """LLMを使ってタスクを分解

        Returns:
            タスク辞書リスト。各辞書は task_id, goal, depends_on を含む。
        """
        from hiveforge.queen_bee.planner import TaskPlanner

        try:
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
        except Exception:
            logger.warning("タスク分解に失敗、単一タスクにフォールバック", exc_info=True)
            return [{"task_id": str(generate_event_id()), "goal": goal, "depends_on": []}]

    async def _execute_task(
        self,
        task_id: str,
        run_id: str,
        goal: str,
        context: dict[str, Any],
        worker: ManagedWorker | None = None,
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
            logger.exception(f"タスク実行エラー: {e}")
            return {
                "status": "error",
                "task_id": task_id,
                "worker_id": worker.worker_id,
                "error": str(e),
            }

    # -------------------------------------------------------------------------
    # LLM統合
    # -------------------------------------------------------------------------

    async def _get_llm_client(self):
        """LLMクライアントを取得（遅延初期化）"""
        if self._llm_client is None:
            from ..llm.client import LLMClient

            self._llm_client = LLMClient(config=self.llm_config)
        return self._llm_client

    async def _get_agent_runner(self):
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

    async def close(self) -> None:
        """リソースを解放"""
        # 全Workerを閉じる
        for worker in self._workers.values():
            await worker.server.close()

        if self._llm_client:
            await self._llm_client.close()
            self._llm_client = None
        self._agent_runner = None

    # -------------------------------------------------------------------------
    # ディスパッチャ
    # -------------------------------------------------------------------------

    async def dispatch_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツール呼び出しをディスパッチ"""
        handlers = {
            "execute_goal": self.handle_execute_goal,
            "plan_tasks": self.handle_plan_tasks,
            "assign_task": self.handle_assign_task,
            "get_colony_status": self.handle_get_colony_status,
            "add_worker": self.handle_add_worker,
            "remove_worker": self.handle_remove_worker,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        return await handler(arguments)
