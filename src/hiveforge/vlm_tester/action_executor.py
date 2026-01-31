"""アクション実行モジュール

Playwright MCP、Playwright直接、またはPyAutoGUIを使用してUI操作を実行します。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from playwright.async_api import Page
    from hiveforge.vlm_tester.playwright_mcp_client import PlaywrightMCPClient


ActionMode = Literal["mcp", "playwright", "pyautogui"]

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

    Playwright MCP、Playwright直接、またはPyAutoGUIを使用してマウス・キーボード操作を実行します。
    """

    def __init__(self, mode: ActionMode | None = None) -> None:
        """ActionExecutorを初期化

        Args:
            mode: 実行モード。Noneの場合は自動検出
        """
        self.mode: ActionMode = mode if mode else self._detect_mode()
        self._page: Page | None = None
        self._mcp_client: PlaywrightMCPClient | None = None

    def _detect_mode(self) -> ActionMode:
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
            RuntimeError: pageまたはmcp_clientが設定されていない場合
        """
        if self.mode == "mcp":
            await self._click_mcp(x, y, button=button, double_click=double_click)
        elif self.mode == "playwright":
            await self._click_playwright(x, y, button=button, double_click=double_click)
        else:
            await self._click_pyautogui(x, y, button=button, double_click=double_click)

    async def _click_mcp(
        self,
        x: int,
        y: int,
        *,
        button: str = "left",
        double_click: bool = False,
    ) -> None:
        """MCP経由でクリック"""
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        # MCP経由で座標クリック（vision modeが必要）
        await self._mcp_client.click_coordinates(x, y)
        if double_click:
            await self._mcp_client.click_coordinates(x, y)

    async def _click_playwright(
        self,
        x: int,
        y: int,
        *,
        button: str = "left",
        double_click: bool = False,
    ) -> None:
        """Playwrightでクリック"""
        if self._page is None:
            raise RuntimeError("Page is not set. Call set_page() first.")

        if double_click:
            await self._page.mouse.dblclick(x, y)
        else:
            await self._page.mouse.click(x, y)

    async def _click_pyautogui(
        self,
        x: int,
        y: int,
        *,
        button: str = "left",
        double_click: bool = False,
    ) -> None:
        """PyAutoGUIでクリック"""
        import pyautogui  # type: ignore

        clicks = 2 if double_click else 1
        pyautogui.click(x, y, button=button, clicks=clicks)

    async def type_text(self, text: str, *, press_enter: bool = False) -> None:
        """テキストを入力

        Args:
            text: 入力するテキスト
            press_enter: 入力後にEnterを押すかどうか

        Raises:
            RuntimeError: pageまたはmcp_clientが設定されていない場合
        """
        if self.mode == "mcp":
            await self._type_mcp(text, press_enter=press_enter)
        elif self.mode == "playwright":
            await self._type_playwright(text, press_enter=press_enter)
        else:
            await self._type_pyautogui(text, press_enter=press_enter)

    async def _type_mcp(self, text: str, *, press_enter: bool = False) -> None:
        """MCP経由でテキスト入力"""
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        # MCPではrefが必要だが、座標ベースの場合はキー入力で代替
        await self._mcp_client.press_key(text)
        if press_enter:
            await self._mcp_client.press_key("Enter")

    async def _type_playwright(self, text: str, *, press_enter: bool = False) -> None:
        """Playwrightでテキスト入力"""
        if self._page is None:
            raise RuntimeError("Page is not set. Call set_page() first.")

        await self._page.keyboard.type(text)
        if press_enter:
            await self._page.keyboard.press("Enter")

    async def _type_pyautogui(self, text: str, *, press_enter: bool = False) -> None:
        """PyAutoGUIでテキスト入力"""
        import pyautogui  # type: ignore

        pyautogui.typewrite(text)
        if press_enter:
            pyautogui.press("enter")

    async def press_key(self, key: str) -> None:
        """キーを押す

        Args:
            key: キー名（例: "escape", "ctrl+s", "alt+f4"）

        Raises:
            RuntimeError: pageまたはmcp_clientが設定されていない場合
        """
        if self.mode == "mcp":
            await self._press_key_mcp(key)
        elif self.mode == "playwright":
            await self._press_key_playwright(key)
        else:
            await self._press_key_pyautogui(key)

    async def _press_key_mcp(self, key: str) -> None:
        """MCP経由でキーを押す"""
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

    async def _press_key_playwright(self, key: str) -> None:
        """Playwrightでキーを押す"""
        if self._page is None:
            raise RuntimeError("Page is not set. Call set_page() first.")

        # 修飾キー + キーの組み合わせを解析
        parts = key.lower().split("+")

        if len(parts) == 1:
            # 単一キー
            key_name = KEY_MAP.get(parts[0], parts[0].capitalize())
            await self._page.keyboard.press(key_name)
        else:
            # 修飾キー付き
            modifiers = [MODIFIER_MAP.get(p, p) for p in parts[:-1]]
            main_key = KEY_MAP.get(parts[-1], parts[-1].upper())

            # 修飾キーを押す
            for mod in modifiers:
                await self._page.keyboard.down(mod)

            # メインキーを押す
            await self._page.keyboard.press(main_key)

            # 修飾キーを離す
            for mod in reversed(modifiers):
                await self._page.keyboard.up(mod)

    async def _press_key_pyautogui(self, key: str) -> None:
        """PyAutoGUIでキーを押す"""
        import pyautogui  # type: ignore

        parts = key.lower().split("+")

        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)

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
            RuntimeError: pageまたはmcp_clientが設定されていない場合
        """
        if self.mode == "mcp":
            await self._scroll_mcp(x, y, delta_x=delta_x, delta_y=delta_y)
        elif self.mode == "playwright":
            await self._scroll_playwright(x, y, delta_x=delta_x, delta_y=delta_y)
        else:
            await self._scroll_pyautogui(x, y, delta_x=delta_x, delta_y=delta_y)

    async def _scroll_mcp(
        self,
        x: int,
        y: int,
        *,
        delta_x: int = 0,
        delta_y: int = 0,
    ) -> None:
        """MCP経由でスクロール"""
        if self._mcp_client is None:
            raise RuntimeError("MCP client is not set. Call set_mcp_client() first.")

        await self._mcp_client.scroll(x, y, delta_x=delta_x, delta_y=delta_y)

    async def _scroll_playwright(
        self,
        x: int,
        y: int,
        *,
        delta_x: int = 0,
        delta_y: int = 0,
    ) -> None:
        """Playwrightでスクロール"""
        if self._page is None:
            raise RuntimeError("Page is not set. Call set_page() first.")

        await self._page.mouse.move(x, y)
        await self._page.mouse.wheel(delta_x, delta_y)

    async def _scroll_pyautogui(
        self,
        x: int,
        y: int,
        *,
        delta_x: int = 0,
        delta_y: int = 0,
    ) -> None:
        """PyAutoGUIでスクロール"""
        import pyautogui  # type: ignore

        pyautogui.moveTo(x, y)
        if delta_y:
            pyautogui.scroll(-delta_y // 100)  # PyAutoGUIは逆方向

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
            RuntimeError: pageが設定されていない場合（playwrightモード）
        """
        if self.mode == "playwright":
            await self._drag_playwright(start_x, start_y, end_x, end_y)
        else:
            await self._drag_pyautogui(start_x, start_y, end_x, end_y)

    async def _drag_playwright(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> None:
        """Playwrightでドラッグ"""
        if self._page is None:
            raise RuntimeError("Page is not set. Call set_page() first.")

        await self._page.mouse.move(start_x, start_y)
        await self._page.mouse.down()
        await self._page.mouse.move(end_x, end_y)
        await self._page.mouse.up()

    async def _drag_pyautogui(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> None:
        """PyAutoGUIでドラッグ"""
        import pyautogui  # type: ignore

        pyautogui.moveTo(start_x, start_y)
        pyautogui.drag(end_x - start_x, end_y - start_y)
