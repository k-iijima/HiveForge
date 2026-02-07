"""Queen Bee MCPサーバー

Colonyを統括し、タスクを分解してWorker Beeに割り当てる。
LLMを使用してタスク分解と進捗管理を行う。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.config import LLMConfig
from ..core.events import (
    TaskCreatedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
)
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

    def __post_init__(self) -> None:
        """初期化"""
        self._llm_client = None
        self._agent_runner = None
        self._workers: dict[str, ManagedWorker] = {}
        self._pending_tasks: list[dict[str, Any]] = []
        self._current_run_id: str | None = None

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
        """
        run_id = arguments.get("run_id", generate_event_id())
        goal = arguments.get("goal", "")
        context = arguments.get("context", {})

        self._current_run_id = run_id

        # Workerがいなければ1つ作成
        if not self._workers:
            self.add_worker(f"worker-{self.colony_id}-1")

        try:
            # LLMでタスク分解（または単純なタスクとしてそのまま実行）
            tasks = await self._plan_tasks(goal, context)

            if not tasks:
                # タスク分解できなかった場合、目標をそのまま1タスクとして実行
                tasks = [{"task_id": generate_event_id(), "goal": goal}]

            results = []
            for task in tasks:
                result = await self._execute_task(
                    task_id=task.get("task_id", generate_event_id()),
                    run_id=run_id,
                    goal=task.get("goal", goal),
                    context=context,
                )
                results.append(result)

            # 全タスクの結果を集約
            success_count = sum(1 for r in results if r.get("status") == "completed")
            total = len(results)

            return {
                "status": "completed" if success_count == total else "partial",
                "run_id": run_id,
                "goal": goal,
                "tasks_total": total,
                "tasks_completed": success_count,
                "results": results,
            }

        except Exception as e:
            logger.exception(f"目標実行エラー: {e}")
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
        """LLMを使ってタスクを分解"""
        # TODO: LLMでタスク分解を実装
        # 現時点では単純に1タスクとして返す
        return [
            {
                "task_id": generate_event_id(),
                "goal": goal,
            }
        ]

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
                return {
                    "status": "completed",
                    "task_id": task_id,
                    "worker_id": worker.worker_id,
                    "result": result.get("result", ""),
                    "llm_output": result.get("llm_output", ""),
                    "tool_calls_made": result.get("tool_calls_made", 0),
                }
            else:
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
            from ..llm.runner import AgentRunner
            from ..core.activity_bus import AgentInfo, AgentRole

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
