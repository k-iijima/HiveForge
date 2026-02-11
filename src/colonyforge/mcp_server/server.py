"""ColonyForge MCP Server

Model Context Protocol (MCP) サーバー実装。
Copilot ChatからHive Coreへのブリッジを提供。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import InitializationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    ServerCapabilities,
    TextContent,
    ToolsCapability,
)

from ..beekeeper.server import BeekeeperMCPServer
from ..core import AkashicRecord, get_settings
from ..core.ar.hive_storage import HiveStore
from .handlers import (
    ColonyHandlers,
    ConferenceHandlers,
    DecisionHandlers,
    GitHubHandlers,
    GuardBeeHandlers,
    HiveHandlers,
    InterventionHandlers,
    LineageHandlers,
    RequirementHandlers,
    RunHandlers,
    TaskHandlers,
)
from .tools import get_tool_definitions

logger = logging.getLogger(__name__)


class ColonyForgeMCPServer:
    """ColonyForge MCP Server

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
        self.server = Server("colonyforge")
        self._ar: AkashicRecord | None = None
        self._hive_store: HiveStore | None = None
        self._beekeeper: BeekeeperMCPServer | None = None
        self._current_run_id: str | None = None

        # ハンドラーを初期化
        self._hive_handlers = HiveHandlers(self)
        self._colony_handlers = ColonyHandlers(self)
        self._run_handlers = RunHandlers(self)
        self._task_handlers = TaskHandlers(self)
        self._requirement_handlers = RequirementHandlers(self)
        self._lineage_handlers = LineageHandlers(self)
        self._decision_handlers = DecisionHandlers(self)
        self._conference_handlers = ConferenceHandlers(self)
        self._intervention_handlers = InterventionHandlers(self)
        self._guard_bee_handlers = GuardBeeHandlers(self)
        self._github_handlers = GitHubHandlers(self)

        self._setup_handlers()

    def _get_ar(self) -> AkashicRecord:
        """Akashic Recordを取得"""
        if self._ar is None:
            settings = get_settings()
            self._ar = AkashicRecord(settings.get_vault_path())
        return self._ar

    def _get_hive_store(self) -> HiveStore:
        """HiveStoreを取得"""
        if self._hive_store is None:
            ar = self._get_ar()
            self._hive_store = HiveStore(ar.vault_path)
        return self._hive_store

    def _get_beekeeper(self) -> BeekeeperMCPServer:
        """BeekeeperMCPServerを取得"""
        if self._beekeeper is None:
            ar = self._get_ar()
            hive_store = self._get_hive_store()
            self._beekeeper = BeekeeperMCPServer(ar=ar, hive_store=hive_store)
        return self._beekeeper

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
                logger.exception("MCP tool execution error: %s", name)
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")],
                    isError=True,
                )

    async def _dispatch_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツール名に応じてハンドラーにディスパッチ"""
        # Hive関連
        if name == "create_hive":
            return await self._hive_handlers.handle_create_hive(arguments)
        elif name == "list_hives":
            return await self._hive_handlers.handle_list_hives(arguments)
        elif name == "get_hive":
            return await self._hive_handlers.handle_get_hive(arguments)
        elif name == "close_hive":
            return await self._hive_handlers.handle_close_hive(arguments)
        # Colony関連
        elif name == "create_colony":
            return await self._colony_handlers.handle_create_colony(arguments)
        elif name == "list_colonies":
            return await self._colony_handlers.handle_list_colonies(arguments)
        elif name == "start_colony":
            return await self._colony_handlers.handle_start_colony(arguments)
        elif name == "complete_colony":
            return await self._colony_handlers.handle_complete_colony(arguments)
        # Run関連
        elif name == "start_run":
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
        # Decision関連
        elif name == "record_decision":
            return await self._decision_handlers.handle_record_decision(arguments)
        # Lineage関連
        elif name == "get_lineage":
            return await self._lineage_handlers.handle_get_lineage(arguments)
        # Conference関連
        elif name == "start_conference":
            return await self._conference_handlers.handle_start_conference(arguments)
        elif name == "end_conference":
            return await self._conference_handlers.handle_end_conference(arguments)
        elif name == "list_conferences":
            return await self._conference_handlers.handle_list_conferences(arguments)
        elif name == "get_conference":
            return await self._conference_handlers.handle_get_conference(arguments)
        # Direct Intervention関連
        elif name == "user_intervene":
            return await self._intervention_handlers.handle_user_intervene(arguments)
        elif name == "queen_escalate":
            return await self._intervention_handlers.handle_queen_escalate(arguments)
        elif name == "beekeeper_feedback":
            return await self._intervention_handlers.handle_beekeeper_feedback(arguments)
        elif name == "list_escalations":
            return await self._intervention_handlers.handle_list_escalations(arguments)
        elif name == "get_escalation":
            return await self._intervention_handlers.handle_get_escalation(arguments)
        # Guard Bee関連
        elif name == "verify_colony":
            return await self._guard_bee_handlers.handle_verify_colony(arguments)
        elif name == "get_guard_report":
            return await self._guard_bee_handlers.handle_get_guard_report(arguments)
        # GitHub Projection関連
        elif name == "sync_run_to_github":
            return await self._github_handlers.handle_sync_run_to_github(arguments)
        elif name == "get_github_sync_status":
            return await self._github_handlers.handle_get_github_sync_status(arguments)
        # Beekeeper関連（@colonyforge Chat Participant 経由）
        elif name == "send_message":
            beekeeper = self._get_beekeeper()
            return await beekeeper.handle_send_message(arguments)
        elif name == "get_beekeeper_status":
            beekeeper = self._get_beekeeper()
            return await beekeeper.handle_get_status(arguments)
        elif name == "approve":
            beekeeper = self._get_beekeeper()
            return await beekeeper.handle_approve(arguments)
        elif name == "reject":
            beekeeper = self._get_beekeeper()
            return await beekeeper.handle_reject(arguments)
        else:
            return {"error": f"Unknown tool: {name}"}

    async def run(self) -> None:  # pragma: no cover
        """サーバーを起動"""
        init_options = InitializationOptions(
            server_name="colonyforge",
            server_version="0.1.0",
            capabilities=ServerCapabilities(
                tools=ToolsCapability(),
            ),
        )
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, init_options)


def main():  # pragma: no cover
    """エントリーポイント"""
    server = ColonyForgeMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":  # pragma: no cover
    main()
