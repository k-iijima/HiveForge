"""Agent UI MCP Server

エージェントがブラウザ/画面を操作・分析するためのMCPサーバー。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

from hiveforge.vlm_tester.screen_capture import ScreenCapture
from hiveforge.vlm_tester.action_executor import ActionExecutor
from hiveforge.vlm_tester.hybrid_analyzer import HybridAnalyzer, AnalysisLevel
from hiveforge.vlm_tester.local_analyzers import DiffAnalyzer
from hiveforge.vlm_tester.playwright_mcp_client import PlaywrightMCPClient, is_mcp_mode


class BrowserSession:
    """ブラウザセッション管理

    PLAYWRIGHT_MCP_URL環境変数が設定されている場合はMCP経由、
    それ以外はPlaywright直接で動作。
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None
        self._mcp_client: PlaywrightMCPClient | None = None
        self._capture: ScreenCapture | None = None
        self._executor: ActionExecutor | None = None
        self._use_mcp = is_mcp_mode()

    async def ensure_browser(self) -> None:
        """ブラウザが起動していなければ起動"""
        if self._capture is not None:
            return

        if self._use_mcp:
            await self._start_mcp()
        else:
            await self._start_playwright()

    async def _start_mcp(self) -> None:
        """MCP経由でブラウザに接続"""
        self._mcp_client = PlaywrightMCPClient()

        self._capture = ScreenCapture(mode="mcp")
        self._capture.set_mcp_client(self._mcp_client)

        self._executor = ActionExecutor(mode="mcp")
        self._executor.set_mcp_client(self._mcp_client)

    async def _start_playwright(self) -> None:
        """Playwright直接でブラウザを起動"""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        headless = os.environ.get("VLM_HEADLESS", "true").lower() != "false"
        self._browser = await self._playwright.chromium.launch(headless=headless)
        self._page = await self._browser.new_page()

        self._capture = ScreenCapture(mode="playwright")
        self._capture.set_page(self._page)

        self._executor = ActionExecutor(mode="playwright")
        self._executor.set_page(self._page)

    async def navigate(self, url: str) -> None:
        """URLに移動"""
        if self._use_mcp:
            if self._mcp_client is None:
                raise RuntimeError("MCP client not initialized")
            await self._mcp_client.navigate(url)
        else:
            if self._page is None:
                raise RuntimeError("Browser not started")
            await self._page.goto(url)

    async def close(self) -> None:
        """ブラウザを閉じる"""
        if self._mcp_client:
            await self._mcp_client.close()
            self._mcp_client = None
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._browser = None
        self._playwright = None
        self._capture = None
        self._executor = None

    @property
    def page(self):
        return self._page

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

    @property
    def using_mcp(self) -> bool:
        return self._use_mcp


class AgentUIMCPServer:
    """Agent UI MCP Server

    エージェントがブラウザ/画面を操作・分析するためのMCPサーバー。
    """

    def __init__(self, captures_dir: str | None = None) -> None:
        self.captures_dir = Path(captures_dir) if captures_dir else Path("./agent_captures")
        self.captures_dir.mkdir(parents=True, exist_ok=True)

        self.server = Server("agent-ui")
        self.session = BrowserSession()
        self.analyzer = HybridAnalyzer()
        self.diff_analyzer = DiffAnalyzer()

        self._last_capture: bytes | None = None
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """MCPハンドラーを設定"""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                # ナビゲーション
                Tool(
                    name="navigate",
                    description="指定URLに移動します",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "移動先URL"},
                        },
                        "required": ["url"],
                    },
                ),
                # キャプチャ・分析
                Tool(
                    name="capture_screen",
                    description="現在の画面をキャプチャします。画像データを返します。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "save": {
                                "type": "boolean",
                                "description": "ファイルに保存するか",
                                "default": True,
                            },
                        },
                    },
                ),
                Tool(
                    name="describe_page",
                    description="現在のページを説明します。VLMで画面を分析して日本語で説明を返します。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "focus": {
                                "type": "string",
                                "description": "特に注目してほしい部分（オプション）",
                            },
                        },
                    },
                ),
                Tool(
                    name="find_element",
                    description="指定した要素の位置を探します。VLMで画面を分析して座標を返します。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "探したい要素の説明（例: 「ログインボタン」「検索欄」）",
                            },
                        },
                        "required": ["description"],
                    },
                ),
                Tool(
                    name="compare_with_previous",
                    description="前回のキャプチャと現在の画面を比較し、変化を報告します。",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                # 操作
                Tool(
                    name="click",
                    description="指定座標またはfind_elementで見つけた要素をクリックします",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer", "description": "X座標"},
                            "y": {"type": "integer", "description": "Y座標"},
                            "element": {
                                "type": "string",
                                "description": "クリックしたい要素の説明（座標の代わりに指定可）",
                            },
                            "double_click": {
                                "type": "boolean",
                                "description": "ダブルクリックするか",
                                "default": False,
                            },
                        },
                    },
                ),
                Tool(
                    name="type_text",
                    description="テキストを入力します",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "入力するテキスト"},
                            "press_enter": {
                                "type": "boolean",
                                "description": "入力後にEnterを押すか",
                                "default": False,
                            },
                        },
                        "required": ["text"],
                    },
                ),
                Tool(
                    name="press_key",
                    description="キーを押します（例: escape, ctrl+s, enter）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "キー名"},
                        },
                        "required": ["key"],
                    },
                ),
                Tool(
                    name="scroll",
                    description="画面をスクロールします",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": ["up", "down", "left", "right"],
                                "description": "スクロール方向",
                            },
                            "amount": {
                                "type": "integer",
                                "description": "スクロール量（ピクセル）",
                                "default": 300,
                            },
                        },
                        "required": ["direction"],
                    },
                ),
                # 待機
                Tool(
                    name="wait_for_element",
                    description="指定した要素が表示されるまで待機します",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "待機する要素の説明",
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "タイムアウト秒数",
                                "default": 10,
                            },
                        },
                        "required": ["description"],
                    },
                ),
                # セッション管理
                Tool(
                    name="close_browser",
                    description="ブラウザを閉じます",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                # 履歴
                Tool(
                    name="list_captures",
                    description="保存されたキャプチャの一覧を返します",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "取得する最大数",
                                "default": 10,
                            },
                        },
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent | ImageContent]:
            handlers = {
                "navigate": self._handle_navigate,
                "capture_screen": self._handle_capture_screen,
                "describe_page": self._handle_describe_page,
                "find_element": self._handle_find_element,
                "compare_with_previous": self._handle_compare,
                "click": self._handle_click,
                "type_text": self._handle_type_text,
                "press_key": self._handle_press_key,
                "scroll": self._handle_scroll,
                "wait_for_element": self._handle_wait_for_element,
                "close_browser": self._handle_close_browser,
                "list_captures": self._handle_list_captures,
            }

            handler = handlers.get(name)
            if handler:
                return await handler(arguments)
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _handle_navigate(self, args: dict[str, Any]) -> list[TextContent]:
        """URLに移動"""
        await self.session.ensure_browser()
        url = args["url"]
        await self.session.navigate(url)
        mode = "MCP" if self.session.using_mcp else "Playwright"
        return [TextContent(type="text", text=f"Navigated to: {url} (via {mode})")]

    async def _handle_capture_screen(
        self, args: dict[str, Any]
    ) -> list[TextContent | ImageContent]:
        """画面をキャプチャ"""
        await self.session.ensure_browser()

        image_data = await self.session.capture.capture()
        self._last_capture = image_data

        result: list[TextContent | ImageContent] = []

        if args.get("save", True):
            filepath = self._save_capture(image_data, {"action": "capture_screen"})
            result.append(TextContent(type="text", text=f"Saved: {filepath}"))

        # 画像をbase64で返す
        image_base64 = base64.b64encode(image_data).decode("utf-8")
        result.append(
            ImageContent(
                type="image",
                data=image_base64,
                mimeType="image/png",
            )
        )

        return result

    async def _handle_describe_page(self, args: dict[str, Any]) -> list[TextContent | ImageContent]:
        """ページを説明"""
        await self.session.ensure_browser()

        image_data = await self.session.capture.capture()
        self._last_capture = image_data

        focus = args.get("focus", "")
        prompt = "この画面を日本語で説明してください。"
        if focus:
            prompt += f" 特に「{focus}」に注目してください。"

        # VLM分析
        result = await self.analyzer.analyze(
            image_data,
            prompt,
            level=AnalysisLevel.HYBRID,
        )

        # 画像も返す
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        return [
            ImageContent(type="image", data=image_base64, mimeType="image/png"),
            TextContent(type="text", text=result.combined_text or "（分析結果なし）"),
        ]

    async def _handle_find_element(self, args: dict[str, Any]) -> list[TextContent]:
        """要素を探す"""
        await self.session.ensure_browser()

        image_data = await self.session.capture.capture()
        description = args["description"]

        prompt = f"""この画面で「{description}」の位置を特定してください。
見つかった場合は以下のJSON形式で回答してください:
{{"found": true, "x": X座標, "y": Y座標, "description": "要素の説明"}}

見つからない場合は:
{{"found": false, "reason": "見つからない理由"}}
"""

        result = await self.analyzer.analyze(
            image_data,
            prompt,
            level=AnalysisLevel.HYBRID,
        )

        return [
            TextContent(
                type="text", text=result.combined_text or '{"found": false, "reason": "分析失敗"}'
            )
        ]

    async def _handle_compare(self, args: dict[str, Any]) -> list[TextContent | ImageContent]:
        """前回と比較"""
        await self.session.ensure_browser()

        if self._last_capture is None:
            return [
                TextContent(
                    type="text",
                    text="前回のキャプチャがありません。先にcapture_screenを実行してください。",
                )
            ]

        current = await self.session.capture.capture()
        previous = self._last_capture
        self._last_capture = current

        # 差分分析
        diff_result = await self.diff_analyzer.compare(previous, current)

        if diff_result.data.get("is_same"):
            return [TextContent(type="text", text="画面に変化はありません。")]

        # 差分画像を生成
        diff_image = await self.diff_analyzer.create_diff_image(previous, current)

        result: list[TextContent | ImageContent] = []

        if diff_image:
            diff_base64 = base64.b64encode(diff_image).decode("utf-8")
            result.append(ImageContent(type="image", data=diff_base64, mimeType="image/png"))

        result.append(
            TextContent(
                type="text",
                text=f"画面に変化があります。差分率: {diff_result.data.get('diff_ratio', 0):.2%}",
            )
        )

        return result

    async def _handle_click(self, args: dict[str, Any]) -> list[TextContent]:
        """クリック"""
        await self.session.ensure_browser()

        x = args.get("x")
        y = args.get("y")
        element = args.get("element")
        double_click = args.get("double_click", False)

        # 要素指定の場合はfind_elementで座標を取得
        if element and (x is None or y is None):
            find_result = await self._handle_find_element({"description": element})
            text = find_result[0].text if find_result else ""

            try:
                data = json.loads(text)
                if data.get("found"):
                    x = data["x"]
                    y = data["y"]
                else:
                    return [TextContent(type="text", text=f"要素が見つかりませんでした: {element}")]
            except json.JSONDecodeError:
                return [
                    TextContent(type="text", text=f"要素の位置を特定できませんでした: {element}")
                ]

        if x is None or y is None:
            return [
                TextContent(type="text", text="座標(x, y)または要素(element)を指定してください")
            ]

        await self.session.executor.click(x, y, double_click=double_click)

        action = "ダブルクリック" if double_click else "クリック"
        return [TextContent(type="text", text=f"{action}しました: ({x}, {y})")]

    async def _handle_type_text(self, args: dict[str, Any]) -> list[TextContent]:
        """テキスト入力"""
        await self.session.ensure_browser()

        text = args["text"]
        press_enter = args.get("press_enter", False)

        await self.session.executor.type_text(text, press_enter=press_enter)

        msg = f"入力しました: {text}"
        if press_enter:
            msg += " (Enter押下)"
        return [TextContent(type="text", text=msg)]

    async def _handle_press_key(self, args: dict[str, Any]) -> list[TextContent]:
        """キー入力"""
        await self.session.ensure_browser()

        key = args["key"]
        await self.session.executor.press_key(key)

        return [TextContent(type="text", text=f"キーを押しました: {key}")]

    async def _handle_scroll(self, args: dict[str, Any]) -> list[TextContent]:
        """スクロール"""
        await self.session.ensure_browser()

        direction = args["direction"]
        amount = args.get("amount", 300)

        # ページ中央でスクロール（MCPモードではpageがNoneなのでフォールバック値を使用）
        viewport = None
        if self.session.page is not None:
            viewport = self.session.page.viewport_size
        x = viewport["width"] // 2 if viewport else 400
        y = viewport["height"] // 2 if viewport else 300

        delta_x = 0
        delta_y = 0
        if direction == "down":
            delta_y = amount
        elif direction == "up":
            delta_y = -amount
        elif direction == "right":
            delta_x = amount
        elif direction == "left":
            delta_x = -amount

        await self.session.executor.scroll(x, y, delta_x=delta_x, delta_y=delta_y)

        return [TextContent(type="text", text=f"スクロールしました: {direction} ({amount}px)")]

    async def _handle_wait_for_element(self, args: dict[str, Any]) -> list[TextContent]:
        """要素を待機"""
        await self.session.ensure_browser()

        description = args["description"]
        timeout = args.get("timeout", 10)

        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return [
                    TextContent(
                        type="text", text=f"タイムアウト: {description} が見つかりませんでした"
                    )
                ]

            find_result = await self._handle_find_element({"description": description})
            text = find_result[0].text if find_result else ""

            try:
                data = json.loads(text)
                if data.get("found"):
                    return [
                        TextContent(
                            type="text",
                            text=f"要素が見つかりました: {description} at ({data['x']}, {data['y']})",
                        )
                    ]
            except json.JSONDecodeError:
                pass

            await asyncio.sleep(1)

    async def _handle_close_browser(self, args: dict[str, Any]) -> list[TextContent]:
        """ブラウザを閉じる"""
        await self.session.close()
        return [TextContent(type="text", text="ブラウザを閉じました")]

    async def _handle_list_captures(self, args: dict[str, Any]) -> list[TextContent]:
        """キャプチャ一覧"""
        limit = args.get("limit", 10)

        files = sorted(self.captures_dir.glob("*.json"), reverse=True)[:limit]

        captures = []
        for f in files:
            try:
                data = json.loads(f.read_text())
                captures.append(
                    {
                        "timestamp": data.get("timestamp"),
                        "action": data.get("action"),
                        "image": data.get("image_file"),
                    }
                )
            except Exception:
                pass

        return [TextContent(type="text", text=json.dumps(captures, indent=2, ensure_ascii=False))]

    def _save_capture(self, image_data: bytes, metadata: dict[str, Any]) -> str:
        """キャプチャを保存"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

        image_path = self.captures_dir / f"{timestamp}.png"
        image_path.write_bytes(image_data)

        meta_path = self.captures_dir / f"{timestamp}.json"
        metadata["timestamp"] = timestamp
        metadata["image_file"] = image_path.name
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        return str(image_path)

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
