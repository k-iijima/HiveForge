"""HiveForge MCP Server

Model Context Protocol (MCP) サーバー実装。
Copilot ChatからHive Coreへのブリッジを提供。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)
from pydantic import AnyUrl

from ..core import (
    AkashicRecord,
    EventType,
    build_run_projection,
    generate_event_id,
    get_settings,
)
from ..core.events import (
    RunStartedEvent,
    RunCompletedEvent,
    TaskCreatedEvent,
    TaskAssignedEvent,
    TaskProgressedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    HeartbeatEvent,
    RequirementCreatedEvent,
)
from ..core.ar.projections import RunState, TaskState


class HiveForgeMCPServer:
    """HiveForge MCP Server

    MCPプロトコルを介してCopilot ChatとHive Coreを接続。

    提供ツール:
    - start_run: 新しいRunを開始
    - get_run_status: Run状態を取得
    - create_task: Taskを作成
    - complete_task: Taskを完了
    - fail_task: Taskを失敗
    - report_progress: 進捗を報告
    - create_requirement: 要件確認を作成
    - heartbeat: ハートビートを送信
    """

    def __init__(self):
        self.server = Server("hiveforge")
        self._ar: AkashicRecord | None = None
        self._current_run_id: str | None = None
        self._setup_handlers()

    def _get_ar(self) -> AkashicRecord:
        """Akashic Recordを取得"""
        if self._ar is None:
            settings = get_settings()
            self._ar = AkashicRecord(settings.get_vault_path())
        return self._ar

    def _setup_handlers(self) -> None:
        """MCPハンドラーを設定"""

        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            """利用可能なツール一覧"""
            return ListToolsResult(
                tools=[
                    Tool(
                        name="start_run",
                        description="新しいRunを開始します。goalには達成したい目標を記述してください。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "goal": {
                                    "type": "string",
                                    "description": "このRunで達成したい目標",
                                },
                            },
                            "required": ["goal"],
                        },
                    ),
                    Tool(
                        name="get_run_status",
                        description="現在のRun状態を取得します。タスクの進捗状況や次にやるべきことを確認できます。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "run_id": {
                                    "type": "string",
                                    "description": "Run ID（省略時は現在のRun）",
                                },
                            },
                        },
                    ),
                    Tool(
                        name="create_task",
                        description="新しいTaskを作成します。分解した作業単位を登録してください。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "タスクのタイトル",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "タスクの詳細説明",
                                },
                            },
                            "required": ["title"],
                        },
                    ),
                    Tool(
                        name="assign_task",
                        description="Taskを自分に割り当てて作業を開始します。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "task_id": {
                                    "type": "string",
                                    "description": "タスクID",
                                },
                            },
                            "required": ["task_id"],
                        },
                    ),
                    Tool(
                        name="report_progress",
                        description="Taskの進捗を報告します。0-100の数値で進捗率を指定してください。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "task_id": {
                                    "type": "string",
                                    "description": "タスクID",
                                },
                                "progress": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 100,
                                    "description": "進捗率 (0-100)",
                                },
                                "message": {
                                    "type": "string",
                                    "description": "進捗メッセージ",
                                },
                            },
                            "required": ["task_id", "progress"],
                        },
                    ),
                    Tool(
                        name="complete_task",
                        description="Taskを完了します。成果物や結果を記録してください。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "task_id": {
                                    "type": "string",
                                    "description": "タスクID",
                                },
                                "result": {
                                    "type": "string",
                                    "description": "タスクの成果・結果",
                                },
                            },
                            "required": ["task_id"],
                        },
                    ),
                    Tool(
                        name="fail_task",
                        description="Taskを失敗としてマークします。エラー内容を記録してください。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "task_id": {
                                    "type": "string",
                                    "description": "タスクID",
                                },
                                "error": {
                                    "type": "string",
                                    "description": "エラー内容",
                                },
                                "retryable": {
                                    "type": "boolean",
                                    "description": "リトライ可能かどうか",
                                    "default": True,
                                },
                            },
                            "required": ["task_id", "error"],
                        },
                    ),
                    Tool(
                        name="create_requirement",
                        description="ユーザーへの確認が必要な要件を作成します。承認待ちになります。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "description": {
                                    "type": "string",
                                    "description": "確認したい内容",
                                },
                                "options": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "選択肢（任意）",
                                },
                            },
                            "required": ["description"],
                        },
                    ),
                    Tool(
                        name="complete_run",
                        description="Runを完了します。全てのTaskが完了したら呼び出してください。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "summary": {
                                    "type": "string",
                                    "description": "Runの完了サマリー",
                                },
                            },
                        },
                    ),
                    Tool(
                        name="heartbeat",
                        description="ハートビートを送信して沈黙を防ぎます。長時間の処理中に呼び出してください。",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "現在の状況",
                                },
                            },
                        },
                    ),
                ]
            )

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
            """ツールを実行"""
            try:
                handler = getattr(self, f"_handle_{name}", None)
                if handler is None:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"Unknown tool: {name}")]
                    )
                result = await handler(arguments)
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
                )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Error: {str(e)}")]
                )

    async def _handle_start_run(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run開始"""
        ar = self._get_ar()
        run_id = generate_event_id()
        goal = args.get("goal", "")

        event = RunStartedEvent(
            run_id=run_id,
            actor="copilot",
            payload={"goal": goal},
        )
        ar.append(event, run_id)

        self._current_run_id = run_id

        return {
            "status": "started",
            "run_id": run_id,
            "goal": goal,
            "message": f"Run '{run_id}' を開始しました。目標: {goal}",
        }

    async def _handle_get_run_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run状態取得"""
        ar = self._get_ar()
        run_id = args.get("run_id") or self._current_run_id

        if not run_id:
            return {"error": "No active run. Use start_run first."}

        events = list(ar.replay(run_id))
        if not events:
            return {"error": f"Run {run_id} not found"}

        proj = build_run_projection(events, run_id)

        pending_tasks = [{"id": t.id, "title": t.title} for t in proj.pending_tasks]
        in_progress_tasks = [
            {"id": t.id, "title": t.title, "progress": t.progress, "assignee": t.assignee}
            for t in proj.in_progress_tasks
        ]
        completed_tasks = [{"id": t.id, "title": t.title} for t in proj.completed_tasks]
        blocked_tasks = [{"id": t.id, "title": t.title} for t in proj.blocked_tasks]
        pending_reqs = [{"id": r.id, "description": r.description} for r in proj.pending_requirements]

        return {
            "run_id": run_id,
            "goal": proj.goal,
            "state": proj.state.value,
            "event_count": proj.event_count,
            "tasks": {
                "pending": pending_tasks,
                "in_progress": in_progress_tasks,
                "completed": completed_tasks,
                "blocked": blocked_tasks,
            },
            "pending_requirements": pending_reqs,
            "last_heartbeat": proj.last_heartbeat.isoformat() if proj.last_heartbeat else None,
        }

    async def _handle_create_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task作成"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = generate_event_id()

        event = TaskCreatedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            payload={
                "title": args.get("title", ""),
                "description": args.get("description", ""),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "created",
            "task_id": task_id,
            "title": args.get("title", ""),
        }

    async def _handle_assign_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task割り当て"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")
        if not task_id:
            return {"error": "task_id is required"}

        event = TaskAssignedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            payload={"assignee": "copilot"},
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "assigned",
            "task_id": task_id,
        }

    async def _handle_report_progress(self, args: dict[str, Any]) -> dict[str, Any]:
        """進捗報告"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")
        progress = args.get("progress", 0)

        if not task_id:
            return {"error": "task_id is required"}

        event = TaskProgressedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            payload={
                "progress": progress,
                "message": args.get("message", ""),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "progressed",
            "task_id": task_id,
            "progress": progress,
        }

    async def _handle_complete_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task完了"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")

        if not task_id:
            return {"error": "task_id is required"}

        event = TaskCompletedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            payload={"result": args.get("result", "")},
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "completed",
            "task_id": task_id,
        }

    async def _handle_fail_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task失敗"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")

        if not task_id:
            return {"error": "task_id is required"}

        event = TaskFailedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            payload={
                "error": args.get("error", ""),
                "retryable": args.get("retryable", True),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "failed",
            "task_id": task_id,
            "error": args.get("error", ""),
        }

    async def _handle_create_requirement(self, args: dict[str, Any]) -> dict[str, Any]:
        """要件作成"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        req_id = generate_event_id()

        event = RequirementCreatedEvent(
            run_id=self._current_run_id,
            actor="copilot",
            payload={
                "requirement_id": req_id,
                "description": args.get("description", ""),
                "options": args.get("options", []),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "created",
            "requirement_id": req_id,
            "description": args.get("description", ""),
            "message": "ユーザーの承認を待っています。",
        }

    async def _handle_complete_run(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run完了"""
        if not self._current_run_id:
            return {"error": "No active run."}

        ar = self._get_ar()

        event = RunCompletedEvent(
            run_id=self._current_run_id,
            actor="copilot",
            payload={"summary": args.get("summary", "")},
        )
        ar.append(event, self._current_run_id)

        run_id = self._current_run_id
        self._current_run_id = None

        return {
            "status": "completed",
            "run_id": run_id,
            "summary": args.get("summary", ""),
        }

    async def _handle_heartbeat(self, args: dict[str, Any]) -> dict[str, Any]:
        """ハートビート"""
        if not self._current_run_id:
            return {"error": "No active run."}

        ar = self._get_ar()

        event = HeartbeatEvent(
            run_id=self._current_run_id,
            actor="copilot",
            payload={"message": args.get("message", "")},
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def run(self) -> None:
        """サーバーを起動"""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream)


def main():
    """エントリーポイント"""
    server = HiveForgeMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
