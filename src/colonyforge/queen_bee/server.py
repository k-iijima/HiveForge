"""Queen Bee MCPサーバー

Colonyを統括し、タスクを分解してWorker Beeに割り当てる。
LLMを使用してタスク分解と進捗管理を行う。

実装は以下のMixinに分割:
- ExecutionMixin: 目標実行 + 直接実行パス
- PipelineExecutionMixin: Pipeline経由実行 + 承認再開
- TaskRunnerMixin: タスク実行 + LLM初期化
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..core import AkashicRecord
from ..core.config import LLMConfig
from ..core.models.action_class import TrustLevel
from ..worker_bee.models import WorkerState
from ..worker_bee.server import WorkerBeeMCPServer
from .execution import ExecutionMixin
from .pipeline_execution import PipelineExecutionMixin
from .task_runner import TaskRunnerMixin

logger = logging.getLogger(__name__)


@dataclass
class ManagedWorker:
    """管理対象のWorker Bee"""

    worker_id: str
    server: WorkerBeeMCPServer
    current_task_id: str | None = None


@dataclass
class QueenBeeMCPServer(
    ExecutionMixin,
    PipelineExecutionMixin,
    TaskRunnerMixin,
):
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
        from ..llm.client import LLMClient
        from ..llm.runner import AgentRunner

        self._llm_client: LLMClient | None = None
        self._agent_runner: AgentRunner | None = None
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
    # 追加ハンドラ
    # -------------------------------------------------------------------------

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
