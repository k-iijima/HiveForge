"""Worker Bee MCPサーバー

Worker Beeの状態を管理し、Queen Beeとの通信を処理する。
LLMを使用してタスクを自律的に実行する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.config import LLMConfig
from ..core.events import (
    EventType,
    WorkerAssignedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerProgressEvent,
    WorkerStartedEvent,
)

logger = logging.getLogger(__name__)


class WorkerState(str, Enum):
    """Worker Beeの状態"""

    IDLE = "idle"  # タスク待ち
    WORKING = "working"  # 作業中
    ERROR = "error"  # エラー状態


@dataclass
class WorkerContext:
    """Worker Beeのコンテキスト"""

    worker_id: str
    state: WorkerState = WorkerState.IDLE
    current_task_id: str | None = None
    current_run_id: str | None = None
    progress: int = 0


@dataclass
class WorkerBeeMCPServer:
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
        self._llm_client = None
        self._agent_runner = None

    @property
    def state(self) -> WorkerState:
        """現在の状態を取得"""
        return self.context.state

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """MCPツール定義を取得"""
        return [
            {
                "name": "receive_task",
                "description": "Queen Beeからタスクを受け取る",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "タスクID"},
                        "run_id": {"type": "string", "description": "Run ID"},
                        "goal": {"type": "string", "description": "タスクの目標"},
                        "context": {
                            "type": "object",
                            "description": "タスクのコンテキスト情報",
                        },
                    },
                    "required": ["task_id", "run_id", "goal"],
                },
            },
            {
                "name": "report_progress",
                "description": "作業の進捗を報告する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "progress": {
                            "type": "integer",
                            "description": "進捗率 (0-100)",
                            "minimum": 0,
                            "maximum": 100,
                        },
                        "message": {"type": "string", "description": "進捗メッセージ"},
                    },
                    "required": ["progress"],
                },
            },
            {
                "name": "complete_task",
                "description": "タスクを完了として報告する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "string", "description": "作業結果"},
                        "deliverables": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "成果物のリスト",
                        },
                    },
                    "required": ["result"],
                },
            },
            {
                "name": "fail_task",
                "description": "タスクの失敗を報告する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "失敗理由"},
                        "recoverable": {
                            "type": "boolean",
                            "description": "リカバリ可能か",
                        },
                    },
                    "required": ["reason"],
                },
            },
            {
                "name": "get_status",
                "description": "Worker Beeの現在の状態を取得",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "execute_task_with_llm",
                "description": "タスクを受け取りLLMで自律的に実行する（ワンショット）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "タスクID"},
                        "run_id": {"type": "string", "description": "Run ID"},
                        "goal": {"type": "string", "description": "タスクの目標（自然言語）"},
                        "context": {
                            "type": "object",
                            "description": "タスクのコンテキスト情報",
                            "properties": {
                                "working_directory": {"type": "string"},
                            },
                        },
                    },
                    "required": ["task_id", "run_id", "goal"],
                },
            },
        ]

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
            from ..llm.tools import get_basic_tools

            client = await self._get_llm_client()
            self._agent_runner = AgentRunner(client, agent_type="worker_bee")

            # 基本ツールを登録
            for tool in get_basic_tools():
                self._agent_runner.register_tool(tool)

        return self._agent_runner

    async def run_with_llm(
        self, goal: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """LLMを使用してタスクを自律実行

        Args:
            goal: タスクの目標（自然言語）
            context: 追加コンテキスト情報

        Returns:
            実行結果
        """
        from ..llm.runner import AgentContext

        runner = await self._get_agent_runner()

        # コンテキストを構築
        agent_context = AgentContext(
            run_id=self.context.current_run_id or "standalone",
            task_id=self.context.current_task_id,
            working_directory=context.get("working_directory", ".") if context else ".",
            metadata=context or {},
        )

        # 進捗報告: 開始
        await self.handle_report_progress({"progress": 10, "message": "LLMで思考中..."})

        try:
            # LLMで実行
            result = await runner.run(goal, agent_context)

            # 進捗報告: 完了
            await self.handle_report_progress({"progress": 100, "message": "実行完了"})

            if result.success:
                return {
                    "status": "success",
                    "output": result.output,
                    "tool_calls_made": result.tool_calls_made,
                }
            else:
                return {
                    "status": "error",
                    "error": result.error,
                    "tool_calls_made": result.tool_calls_made,
                }

        except Exception as e:
            logger.exception(f"LLM実行エラー: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def execute_task_with_llm(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """タスクを受け取りLLMで自律実行（ワンショット）

        receive_task + run_with_llm + complete_task/fail_task を一括実行
        """
        # タスクを受け取る
        receive_result = await self.handle_receive_task(arguments)
        if "error" in receive_result:
            return receive_result

        goal = arguments.get("goal", "")
        context = arguments.get("context", {})

        # LLMで実行
        llm_result = await self.run_with_llm(goal, context)

        # 結果に応じて完了/失敗を報告
        if llm_result.get("status") == "success":
            complete_result = await self.handle_complete_task(
                {
                    "result": llm_result.get("output", ""),
                    "deliverables": [],
                }
            )
            return {
                **complete_result,
                "llm_output": llm_result.get("output"),
                "tool_calls_made": llm_result.get("tool_calls_made", 0),
            }
        else:
            fail_result = await self.handle_fail_task(
                {
                    "reason": llm_result.get("error", "Unknown error"),
                    "recoverable": True,
                }
            )
            return {
                **fail_result,
                "llm_error": llm_result.get("error"),
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
            "execute_task_with_llm": self.execute_task_with_llm,  # 新規追加
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        return await handler(arguments)
