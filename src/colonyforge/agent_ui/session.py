"""ブラウザセッション管理

Playwright MCP経由でブラウザを操作。
"""

from __future__ import annotations

from colonyforge.vlm_tester.action_executor import ActionExecutor
from colonyforge.vlm_tester.playwright_mcp_client import PlaywrightMCPClient
from colonyforge.vlm_tester.screen_capture import ScreenCapture


class BrowserSession:
    """ブラウザセッション管理

    Playwright MCP経由でブラウザを操作します。
    """

    def __init__(self) -> None:
        self._mcp_client: PlaywrightMCPClient | None = None
        self._capture: ScreenCapture | None = None
        self._executor: ActionExecutor | None = None

    async def ensure_browser(self) -> None:
        """MCPクライアントが初期化されていなければ初期化"""
        if self._capture is not None:
            return

        self._mcp_client = PlaywrightMCPClient()

        self._capture = ScreenCapture()
        self._capture.set_mcp_client(self._mcp_client)

        self._executor = ActionExecutor()
        self._executor.set_mcp_client(self._mcp_client)

    async def navigate(self, url: str) -> None:
        """URLに移動"""
        if self._mcp_client is None:
            raise RuntimeError("MCP client not initialized")
        await self._mcp_client.navigate(url)

    async def close(self) -> None:
        """ブラウザを閉じる"""
        if self._mcp_client:
            await self._mcp_client.close()
            self._mcp_client = None
        self._capture = None
        self._executor = None

    @property
    def mcp_client(self) -> PlaywrightMCPClient | None:
        return self._mcp_client

    @property
    def capture(self) -> ScreenCapture:
        if self._capture is None:
            raise RuntimeError("Browser not started")
        return self._capture

    @property
    def executor(self) -> ActionExecutor:
        if self._executor is None:
            raise RuntimeError("Browser not started")
        return self._executor
