"""画面キャプチャモジュール

Playwright MCP経由で画面をキャプチャします。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from colonyforge.vlm_tester.playwright_mcp_client import PlaywrightMCPClient


class ScreenCapture:
    """画面キャプチャクラス

    Playwright MCP経由で画面をキャプチャします。
    """

    def __init__(self) -> None:
        """ScreenCaptureを初期化"""
        self._mcp_client: PlaywrightMCPClient | None = None

    def set_mcp_client(self, client: PlaywrightMCPClient) -> None:
        """MCP clientを設定

        Args:
            client: PlaywrightMCPClientインスタンス
        """
        self._mcp_client = client

    async def capture(self, region: tuple[int, int, int, int] | None = None) -> bytes:
        """画面をキャプチャ

        Args:
            region: キャプチャ領域 (x, y, width, height)。Noneの場合は全画面
                   ※現在MCPではサポートされていないため無視される

        Returns:
            PNG形式の画像データ

        Raises:
            RuntimeError: mcp_clientが設定されていない場合
        """
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        return await self._mcp_client.screenshot()
