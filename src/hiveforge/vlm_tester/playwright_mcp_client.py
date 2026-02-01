"""Playwright MCP Client

Playwright MCPサーバー（Dockerコンテナ）と通信するクライアント。
ローカルにPlaywrightをインストールせずにブラウザ操作が可能。
"""

from __future__ import annotations

import base64
import os
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client


class PlaywrightMCPClient:
    """Playwright MCPクライアント

    Playwright MCPサーバーとSSEで通信してブラウザを操作します。

    使用例:
        async with PlaywrightMCPClient("http://localhost:8931") as client:
            await client.navigate("https://example.com")
            screenshot = await client.screenshot()
    """

    def __init__(self, server_url: str | None = None) -> None:
        """クライアントを初期化

        Args:
            server_url: MCPサーバーのURL。Noneの場合は環境変数から取得
        """
        self.server_url = server_url or os.environ.get(
            "PLAYWRIGHT_MCP_URL", "http://localhost:8931"
        )
        self._session: ClientSession | None = None
        self._read = None
        self._write = None
        self._streams_cm = None

    async def _ensure_connected(self) -> None:
        """接続されていなければ接続"""
        if self._session is not None:
            return

        sse_url = f"{self.server_url}/sse"
        self._streams_cm = sse_client(sse_url)
        self._read, self._write = await self._streams_cm.__aenter__()

        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def _call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """MCPツールを呼び出す

        Args:
            name: ツール名
            arguments: ツールの引数

        Returns:
            ツールの戻り値
        """
        await self._ensure_connected()
        if self._session is None:
            raise RuntimeError("Session not initialized")

        result = await self._session.call_tool(name, arguments or {})
        return result

    async def navigate(self, url: str) -> dict[str, Any]:
        """URLに移動

        Args:
            url: 移動先URL

        Returns:
            ナビゲーション結果
        """
        result = await self._call_tool("browser_navigate", {"url": url})
        return {"content": result.content if hasattr(result, "content") else []}

    async def screenshot(self) -> bytes:
        """スクリーンショットを取得

        Returns:
            PNG形式の画像データ
        """
        result = await self._call_tool("browser_take_screenshot")

        # レスポンスからbase64画像を抽出
        content = result.content if hasattr(result, "content") else []
        for item in content:
            if hasattr(item, "type") and item.type == "image":
                data = item.data if hasattr(item, "data") else ""
                return base64.b64decode(data)

        raise RuntimeError("Screenshot not returned from MCP server")

    async def snapshot(self) -> str:
        """アクセシビリティスナップショットを取得

        Returns:
            ページのアクセシビリティツリー（テキスト形式）
        """
        result = await self._call_tool("browser_snapshot")

        content = result.content if hasattr(result, "content") else []
        for item in content:
            if hasattr(item, "type") and item.type == "text":
                return item.text if hasattr(item, "text") else ""

        return ""

    async def click(self, ref: str, element: str = "") -> dict[str, Any]:
        """要素をクリック

        Args:
            ref: 要素のref属性（スナップショットから取得）
            element: 要素の説明（ログ用）

        Returns:
            クリック結果
        """
        result = await self._call_tool("browser_click", {"ref": ref, "element": element or ref})
        return {"content": result.content if hasattr(result, "content") else []}

    async def click_coordinates(self, x: int, y: int) -> dict[str, Any]:
        """座標をクリック（vision mode）

        Args:
            x: X座標
            y: Y座標

        Returns:
            クリック結果
        """
        result = await self._call_tool("browser_screen_click", {"x": x, "y": y})
        return {"content": result.content if hasattr(result, "content") else []}

    async def type_text(self, ref: str, text: str, submit: bool = False) -> dict[str, Any]:
        """テキストを入力

        Args:
            ref: 入力要素のref属性
            text: 入力テキスト
            submit: Enterを押すか

        Returns:
            入力結果
        """
        result = await self._call_tool(
            "browser_type",
            {"ref": ref, "text": text, "submit": submit},
        )
        return {"content": result.content if hasattr(result, "content") else []}

    async def press_key(self, key: str) -> dict[str, Any]:
        """キーを押す

        Args:
            key: キー名（例: "Escape", "Enter", "Control+s"）

        Returns:
            キー押下結果
        """
        result = await self._call_tool("browser_press_key", {"key": key})
        return {"content": result.content if hasattr(result, "content") else []}

    async def scroll(
        self, x: int = 0, y: int = 0, delta_x: int = 0, delta_y: int = 0
    ) -> dict[str, Any]:
        """スクロール

        Args:
            x: スクロール開始X座標
            y: スクロール開始Y座標
            delta_x: 水平スクロール量
            delta_y: 垂直スクロール量

        Returns:
            スクロール結果
        """
        result = await self._call_tool(
            "browser_mouse_wheel",
            {"deltaX": delta_x, "deltaY": delta_y},
        )
        return {"content": result.content if hasattr(result, "content") else []}

    async def go_back(self) -> dict[str, Any]:
        """前のページに戻る

        Returns:
            ナビゲーション結果
        """
        result = await self._call_tool("browser_navigate_back")
        return {"content": result.content if hasattr(result, "content") else []}

    async def wait_for_text(self, text: str, timeout: int = 30) -> dict[str, Any]:
        """テキストが表示されるまで待機

        Args:
            text: 待機するテキスト
            timeout: タイムアウト秒数

        Returns:
            待機結果
        """
        result = await self._call_tool(
            "browser_wait_for",
            {"text": text, "timeout": timeout},
        )
        return {"content": result.content if hasattr(result, "content") else []}

    async def close(self) -> None:
        """クライアントを閉じる"""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._streams_cm:
            await self._streams_cm.__aexit__(None, None, None)
            self._streams_cm = None

    async def __aenter__(self) -> PlaywrightMCPClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


def is_mcp_mode() -> bool:
    """MCP経由モードかどうかを判定

    Returns:
        PLAYWRIGHT_MCP_URLが設定されているか
    """
    return bool(os.environ.get("PLAYWRIGHT_MCP_URL"))
