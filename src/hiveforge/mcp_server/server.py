"""HiveForge MCP Server

Model Context Protocol (MCP) サーバー実装。
Copilot ChatからHive Coreへのブリッジを提供。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server, InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    ServerCapabilities,
    TextContent,
    ToolsCapability,
)

from ..core import AkashicRecord, get_settings
from .handlers import RunHandlers, TaskHandlers, RequirementHandlers, LineageHandlers
from .tools import get_tool_definitions


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

        # ハンドラーを初期化
        self._run_handlers = RunHandlers(self)
        self._task_handlers = TaskHandlers(self)
        self._requirement_handlers = RequirementHandlers(self)
        self._lineage_handlers = LineageHandlers(self)

        self._setup_handlers()

    def _get_ar(self) -> AkashicRecord:
        """Akashic Recordを取得"""
        if self._ar is None:
            settings = get_settings()
            self._ar = AkashicRecord(settings.get_vault_path())
        return self._ar

    def _setup_handlers(self) -> None:  # pragma: no cover
        """MCPハンドラーを設定"""

        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            """利用可能なツール一覧"""
            return ListToolsResult(tools=get_tool_definitions())

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
            """ツールを実行"""
            try:
                result = await self._dispatch_tool(name, arguments)
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text", text=json.dumps(result, ensure_ascii=False, indent=2)
                        )
                    ]
                )
            except Exception as e:
                return CallToolResult(content=[TextContent(type="text", text=f"Error: {str(e)}")])

    async def _dispatch_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツール名に応じてハンドラーにディスパッチ"""
        # Run関連
        if name == "start_run":
            return await self._run_handlers.handle_start_run(arguments)
        elif name == "get_run_status":
            return await self._run_handlers.handle_get_run_status(arguments)
        elif name == "complete_run":
            return await self._run_handlers.handle_complete_run(arguments)
        elif name == "heartbeat":
            return await self._run_handlers.handle_heartbeat(arguments)
        elif name == "emergency_stop":
            return await self._run_handlers.handle_emergency_stop(arguments)
        # Task関連
        elif name == "create_task":
            return await self._task_handlers.handle_create_task(arguments)
        elif name == "assign_task":
            return await self._task_handlers.handle_assign_task(arguments)
        elif name == "report_progress":
            return await self._task_handlers.handle_report_progress(arguments)
        elif name == "complete_task":
            return await self._task_handlers.handle_complete_task(arguments)
        elif name == "fail_task":
            return await self._task_handlers.handle_fail_task(arguments)
        # Requirement関連
        elif name == "create_requirement":
            return await self._requirement_handlers.handle_create_requirement(arguments)
        # Lineage関連
        elif name == "get_lineage":
            return await self._lineage_handlers.handle_get_lineage(arguments)
        else:
            return {"error": f"Unknown tool: {name}"}

    async def run(self) -> None:  # pragma: no cover
        """サーバーを起動"""
        init_options = InitializationOptions(
            server_name="hiveforge",
            server_version="0.1.0",
            capabilities=ServerCapabilities(
                tools=ToolsCapability(),
            ),
        )
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, init_options)


def main():  # pragma: no cover
    """エントリーポイント"""
    server = HiveForgeMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":  # pragma: no cover
    main()
