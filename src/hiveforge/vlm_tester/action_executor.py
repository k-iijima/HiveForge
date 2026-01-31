"""アクション実行モジュール

Playwright MCP経由でUI操作を実行します。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from hiveforge.vlm_tester.playwright_mcp_client import PlaywrightMCPClient


# キー名のマッピング（小文字 -> Playwright形式）
KEY_MAP = {
    "escape": "Escape",
    "esc": "Escape",
    "enter": "Enter",
    "return": "Enter",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12",
}

# 修飾キーのマッピング
MODIFIER_MAP = {
    "ctrl": "Control",
    "control": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "meta": "Meta",
    "cmd": "Meta",
    "command": "Meta",
    "win": "Meta",
    "windows": "Meta",
}


class ActionExecutor:
    """アクション実行クラス

    Playwright MCP経由でマウス・キーボード操作を実行します。
    """

    def __init__(self) -> None:
        """ActionExecutorを初期化"""
        self._mcp_client: PlaywrightMCPClient | None = None

    def set_mcp_client(self, client: PlaywrightMCPClient) -> None:
        """MCP clientを設定

        Args:
            client: PlaywrightMCPClientインスタンス
        """
        self._mcp_client = client

    async def click(
        self,
        x: int,
        y: int,
        *,
        button: Literal["left", "right", "middle"] = "left",
        double_click: bool = False,
    ) -> None:
        """指定座標をクリック

        Args:
            x: X座標
            y: Y座標
            button: マウスボタン
            double_click: ダブルクリックするかどうか

        Raises:
            RuntimeError: mcp_clientが設定されていない場合
        """
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        await self._mcp_client.click_coordinates(x, y)
        if double_click:
            await self._mcp_client.click_coordinates(x, y)

    async def type_text(self, text: str, *, press_enter: bool = False) -> None:
        """テキストを入力

        Args:
            text: 入力するテキスト
            press_enter: 入力後にEnterを押すかどうか

        Raises:
            RuntimeError: mcp_clientが設定されていない場合
        """
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        await self._mcp_client.press_key(text)
        if press_enter:
            await self._mcp_client.press_key("Enter")

    async def press_key(self, key: str) -> None:
        """キーを押す

        Args:
            key: キー名（例: "escape", "ctrl+s", "alt+f4"）

        Raises:
            RuntimeError: mcp_clientが設定されていない場合
        """
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        # キー名をMCP形式に変換
        parts = key.lower().split("+")
        if len(parts) == 1:
            key_name = KEY_MAP.get(parts[0], parts[0].capitalize())
        else:
            modifiers = [MODIFIER_MAP.get(p, p) for p in parts[:-1]]
            main_key = KEY_MAP.get(parts[-1], parts[-1].upper())
            key_name = "+".join(modifiers + [main_key])

        await self._mcp_client.press_key(key_name)

    async def scroll(
        self,
        x: int,
        y: int,
        *,
        delta_x: int = 0,
        delta_y: int = 0,
    ) -> None:
        """スクロール

        Args:
            x: X座標
            y: Y座標
            delta_x: 水平スクロール量
            delta_y: 垂直スクロール量

        Raises:
            RuntimeError: mcp_clientが設定されていない場合
        """
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        await self._mcp_client.scroll(x, y, delta_x=delta_x, delta_y=delta_y)

    async def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> None:
        """ドラッグ

        Args:
            start_x: 開始X座標
            start_y: 開始Y座標
            end_x: 終了X座標
            end_y: 終了Y座標

        Raises:
            RuntimeError: mcp_clientが設定されていない場合
        """
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        await self._mcp_client.drag(start_x, start_y, end_x, end_y)
