"""画面キャプチャモジュール

Playwright MCP、Playwright直接、またはPyAutoGUIを使用して画面をキャプチャします。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from playwright.async_api import Page
    from hiveforge.vlm_tester.playwright_mcp_client import PlaywrightMCPClient


CaptureMode = Literal["mcp", "playwright", "pyautogui"]


class ScreenCapture:
    """画面キャプチャクラス

    環境に応じてPlaywright MCP、Playwright直接、またはPyAutoGUIを使用して画面をキャプチャします。
    - PLAYWRIGHT_MCP_URL環境変数がある場合: mcpモード（Dockerコンテナ経由）
    - CODE_SERVER_URL環境変数がある場合: playwrightモード（直接）
    - DISPLAY環境変数がある場合: pyautoguiモード
    """

    def __init__(self, mode: CaptureMode | None = None) -> None:
        """ScreenCaptureを初期化

        Args:
            mode: キャプチャモード。Noneの場合は自動検出
        """
        self.mode: CaptureMode = mode if mode else self._detect_mode()
        self._page: Page | None = None
        self._mcp_client: PlaywrightMCPClient | None = None

    def _detect_mode(self) -> CaptureMode:
        """環境に応じてモードを自動検出"""
        if os.environ.get("PLAYWRIGHT_MCP_URL"):
            return "mcp"
        if os.environ.get("CODE_SERVER_URL"):
            return "playwright"
        if os.environ.get("DISPLAY"):
            return "pyautogui"
        return "mcp"  # デフォルトはMCPモード

    def set_page(self, page: Page) -> None:
        """Playwrightのpageを設定（playwrightモード用）

        Args:
            page: Playwrightのページオブジェクト
        """
        self._page = page

    def set_mcp_client(self, client: PlaywrightMCPClient) -> None:
        """MCP clientを設定（mcpモード用）

        Args:
            client: PlaywrightMCPClientインスタンス
        """
        self._mcp_client = client

    async def capture(self, region: tuple[int, int, int, int] | None = None) -> bytes:
        """画面をキャプチャ

        Args:
            region: キャプチャ領域 (x, y, width, height)。Noneの場合は全画面

        Returns:
            PNG形式の画像データ

        Raises:
            RuntimeError: pageまたはmcp_clientが設定されていない場合
        """
        if self.mode == "mcp":
            return await self._capture_mcp(region)
        elif self.mode == "playwright":
            return await self._capture_playwright(region)
        else:
            return await self._capture_pyautogui(region)

    async def _capture_mcp(self, region: tuple[int, int, int, int] | None = None) -> bytes:
        """MCP経由でキャプチャ"""
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        # MCP経由でスクリーンショットを取得
        # regionは現在MCPではサポートされていないため無視
        return await self._mcp_client.screenshot()

    async def _capture_playwright(self, region: tuple[int, int, int, int] | None = None) -> bytes:
        """Playwrightでキャプチャ"""
        if self._page is None:
            raise RuntimeError("Page is not set. Call set_page() first.")

        if region:
            x, y, width, height = region
            return await self._page.screenshot(
                clip={"x": x, "y": y, "width": width, "height": height}
            )
        return await self._page.screenshot()

    async def _capture_pyautogui(self, region: tuple[int, int, int, int] | None = None) -> bytes:
        """PyAutoGUIでキャプチャ"""
        import io
        import pyautogui  # type: ignore

        if region:
            screenshot = pyautogui.screenshot(region=region)
        else:
            screenshot = pyautogui.screenshot()

        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        return buffer.getvalue()
