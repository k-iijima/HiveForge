"""Agent UI MCP Server

エージェントがブラウザ/画面を操作・分析するためのMCPサーバー。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, ImageContent

from .session import BrowserSession
from .tools import get_tool_definitions
from .handlers import AgentUIHandlers


class AgentUIMCPServer:
    """Agent UI MCP Server

    エージェントがブラウザ/画面を操作・分析するためのMCPサーバー。
    """

    def __init__(self, captures_dir: str | None = None) -> None:
        self.captures_dir = Path(captures_dir) if captures_dir else Path("./agent_captures")
        self.captures_dir.mkdir(parents=True, exist_ok=True)

        self.server = Server("agent-ui")
        self.session = BrowserSession()
        self.handlers = AgentUIHandlers(self.session, self.captures_dir)

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """MCPハンドラーを設定"""

        @self.server.list_tools()
        async def list_tools():
            return get_tool_definitions()

        @self.server.call_tool()
        async def call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent | ImageContent]:
            handler_map = {
                "navigate": self.handlers.handle_navigate,
                "capture_screen": self.handlers.handle_capture_screen,
                "describe_page": self.handlers.handle_describe_page,
                "find_element": self.handlers.handle_find_element,
                "compare_with_previous": self.handlers.handle_compare,
                "click": self.handlers.handle_click,
                "type_text": self.handlers.handle_type_text,
                "press_key": self.handlers.handle_press_key,
                "scroll": self.handlers.handle_scroll,
                "wait_for_element": self.handlers.handle_wait_for_element,
                "close_browser": self.handlers.handle_close_browser,
                "list_captures": self.handlers.handle_list_captures,
            }

            handler = handler_map.get(name)
            if handler:
                return await handler(arguments)
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    # 後方互換性のためのプロパティ
    @property
    def analyzer(self):
        return self.handlers.analyzer

    @property
    def diff_analyzer(self):
        return self.handlers.diff_analyzer

    @property
    def _last_capture(self):
        return self.handlers._last_capture

    @_last_capture.setter
    def _last_capture(self, value):
        self.handlers._last_capture = value

    # 後方互換性のためのハンドラーメソッド（テスト用）
    async def _handle_navigate(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_navigate(args)

    async def _handle_capture_screen(
        self, args: dict[str, Any]
    ) -> list[TextContent | ImageContent]:
        return await self.handlers.handle_capture_screen(args)

    async def _handle_describe_page(
        self, args: dict[str, Any]
    ) -> list[TextContent | ImageContent]:
        return await self.handlers.handle_describe_page(args)

    async def _handle_find_element(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_find_element(args)

    async def _handle_compare(self, args: dict[str, Any]) -> list[TextContent | ImageContent]:
        return await self.handlers.handle_compare(args)

    async def _handle_click(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_click(args)

    async def _handle_type_text(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_type_text(args)

    async def _handle_press_key(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_press_key(args)

    async def _handle_scroll(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_scroll(args)

    async def _handle_wait_for_element(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_wait_for_element(args)

    async def _handle_close_browser(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_close_browser(args)

    async def _handle_list_captures(self, args: dict[str, Any]) -> list[TextContent]:
        return await self.handlers.handle_list_captures(args)

    def _save_capture(self, image_data: bytes, metadata: dict[str, Any]) -> str:
        return self.handlers._save_capture(image_data, metadata)

    async def run(self) -> None:
        """サーバーを起動"""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


def main() -> None:
    """エントリーポイント"""
    import asyncio

    server = AgentUIMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
