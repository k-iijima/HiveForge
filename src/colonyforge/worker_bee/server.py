"""Worker Bee MCPサーバー

Worker Beeの状態を管理し、Queen Beeとの通信を処理する。
LLMを使用してタスクを自律的に実行する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.config import LLMConfig
from ..core.events import (
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerProgressEvent,
    WorkerStartedEvent,
)
from .llm_executor import LLMExecutorMixin
from .models import WorkerContext, WorkerState
from .tool_definitions import get_worker_tool_definitions

logger = logging.getLogger(__name__)


@dataclass
class WorkerBeeMCPServer(LLMExecutorMixin):
    """Worker Bee MCPサーバー

    Queen Beeからタスクを受け取り、作業を実行する。
    MCPプロトコルでQueen Beeと通信する。
    LLMを使用してタスクを自律的に実行できる。
    """

    worker_id: str
    ar: AkashicRecord
    context: WorkerContext = field(init=False)
    llm_config: LLMConfig | None = None  # エージェント別LLM設定

    def __post_init__(self) -> None:
        """初期化"""
        self.context = WorkerContext(worker_id=self.worker_id)
        self._llm_client: Any = None
        self._agent_runner: Any = None

    @property
    def state(self) -> WorkerState:
        """現在の状態を取得"""
        return self.context.state

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """MCPツール定義を取得"""
        return get_worker_tool_definitions()

    async def handle_receive_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """タスク受け取りハンドラ"""
        if self.context.state == WorkerState.WORKING:
            return {
                "error": "Worker is already working on a task",
                "current_task_id": self.context.current_task_id,
            }

        task_id = arguments["task_id"]
        run_id = arguments["run_id"]
        goal = arguments.get("goal", "")

        # 状態を更新
        self.context.state = WorkerState.WORKING
        self.context.current_task_id = task_id
        self.context.current_run_id = run_id
        self.context.progress = 0

        # イベントを発行
        event = WorkerStartedEvent(
            id=generate_event_id(),
            run_id=run_id,
            task_id=task_id,
            worker_id=self.worker_id,
            actor=self.worker_id,
            payload={"goal": goal, "context": arguments.get("context", {})},
        )
        self.ar.append(event, run_id)

        return {
            "status": "accepted",
            "worker_id": self.worker_id,
            "task_id": task_id,
            "message": f"Task {task_id} accepted",
        }

    async def handle_report_progress(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """進捗報告ハンドラ"""
        if self.context.state != WorkerState.WORKING:
            return {"error": "No active task"}

        progress = arguments["progress"]
        message = arguments.get("message", "")

        self.context.progress = progress

        # イベントを発行
        event = WorkerProgressEvent(
            id=generate_event_id(),
            run_id=self.context.current_run_id or "",
            task_id=self.context.current_task_id or "",
            worker_id=self.worker_id,
            actor=self.worker_id,
            progress=progress,
            payload={"message": message},
        )
        if self.context.current_run_id:
            self.ar.append(event, self.context.current_run_id)

        return {
            "status": "reported",
            "progress": progress,
            "message": message,
        }

    async def handle_complete_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """タスク完了ハンドラ"""
        if self.context.state != WorkerState.WORKING:
            return {"error": "No active task"}

        result = arguments.get("result", "")
        deliverables = arguments.get("deliverables", [])

        task_id = self.context.current_task_id
        run_id = self.context.current_run_id

        # イベントを発行
        event = WorkerCompletedEvent(
            id=generate_event_id(),
            run_id=run_id or "",
            task_id=task_id or "",
            worker_id=self.worker_id,
            actor=self.worker_id,
            payload={"result": result, "deliverables": deliverables},
        )
        if run_id:
            self.ar.append(event, run_id)

        # 状態をリセット
        self.context.state = WorkerState.IDLE
        self.context.current_task_id = None
        self.context.current_run_id = None
        self.context.progress = 0

        return {
            "status": "completed",
            "task_id": task_id,
            "result": result,
        }

    async def handle_fail_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """タスク失敗ハンドラ"""
        if self.context.state != WorkerState.WORKING:
            return {"error": "No active task"}

        reason = arguments.get("reason", "Unknown error")
        recoverable = arguments.get("recoverable", False)

        task_id = self.context.current_task_id
        run_id = self.context.current_run_id

        # イベントを発行
        event = WorkerFailedEvent(
            id=generate_event_id(),
            run_id=run_id or "",
            task_id=task_id or "",
            worker_id=self.worker_id,
            actor=self.worker_id,
            reason=reason,
            payload={"recoverable": recoverable},
        )
        if run_id:
            self.ar.append(event, run_id)

        # 状態を更新
        self.context.state = WorkerState.ERROR if not recoverable else WorkerState.IDLE
        self.context.current_task_id = None
        self.context.current_run_id = None
        self.context.progress = 0

        return {
            "status": "failed",
            "task_id": task_id,
            "reason": reason,
            "recoverable": recoverable,
        }

    async def handle_get_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """ステータス取得ハンドラ"""
        return {
            "worker_id": self.worker_id,
            "state": self.context.state.value,
            "current_task_id": self.context.current_task_id,
            "current_run_id": self.context.current_run_id,
            "progress": self.context.progress,
        }

    async def close(self) -> None:
        """リソースを解放"""
        if self._llm_client:
            await self._llm_client.close()
            self._llm_client = None
        self._agent_runner = None

    async def dispatch_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツール呼び出しをディスパッチ"""
        handlers = {
            "receive_task": self.handle_receive_task,
            "report_progress": self.handle_report_progress,
            "complete_task": self.handle_complete_task,
            "fail_task": self.handle_fail_task,
            "get_status": self.handle_get_status,
            "execute_task_with_llm": self.execute_task_with_llm,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        return await handler(arguments)
