"""VLM Tester MCP Serverモジュール

VLM TesterをMCPサーバーとして公開します。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from hiveforge.vlm_tester.action_executor import ActionExecutor
from hiveforge.vlm_tester.hybrid_analyzer import AnalysisLevel, HybridAnalyzer
from hiveforge.vlm_tester.screen_capture import ScreenCapture


class VLMTesterMCPServer:
    """VLM Tester MCP Server

    VLM Tester機能をMCPサーバーとして公開します。
    """

    def __init__(
        self,
        captures_dir: str | None = None,
    ) -> None:
        """VLMTesterMCPServerを初期化

        Args:
            captures_dir: キャプチャ保存ディレクトリ
        """
        self.captures_dir = Path(captures_dir) if captures_dir else Path("./captures")
        self.captures_dir.mkdir(parents=True, exist_ok=True)

        self.server = Server("vlm-tester")
        self.screen_capture = ScreenCapture()
        self.action_executor = ActionExecutor()
        self.analyzer = HybridAnalyzer()

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """MCPハンドラーを設定"""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="capture_screen",
                    description="画面をキャプチャして保存します",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "region": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "integer"},
                                    "y": {"type": "integer"},
                                    "width": {"type": "integer"},
                                    "height": {"type": "integer"},
                                },
                                "description": "キャプチャ領域。省略時は全画面",
                            },
                        },
                    },
                ),
                Tool(
                    name="analyze_screen",
                    description="画面をキャプチャして分析します",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "分析プロンプト",
                            },
                            "level": {
                                "type": "string",
                                "enum": ["local_only", "hybrid", "vlm_ollama", "vlm_cloud"],
                                "description": "分析レベル",
                            },
                        },
                        "required": ["prompt"],
                    },
                ),
                Tool(
                    name="click",
                    description="指定座標をクリックします",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer", "description": "X座標"},
                            "y": {"type": "integer", "description": "Y座標"},
                            "double_click": {
                                "type": "boolean",
                                "description": "ダブルクリックするかどうか",
                            },
                        },
                        "required": ["x", "y"],
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
                                "description": "入力後にEnterを押すかどうか",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                Tool(
                    name="press_key",
                    description="キーを押します",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "キー名（例: escape, ctrl+s）",
                            },
                        },
                        "required": ["key"],
                    },
                ),
                Tool(
                    name="list_captures",
                    description="保存されたキャプチャの一覧を取得します",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            if name == "capture_screen":
                return await self._handle_capture_screen(arguments)
            elif name == "analyze_screen":
                return await self._handle_analyze_screen(arguments)
            elif name == "click":
                return await self._handle_click(arguments)
            elif name == "type_text":
                return await self._handle_type_text(arguments)
            elif name == "press_key":
                return await self._handle_press_key(arguments)
            elif name == "list_captures":
                return await self._handle_list_captures(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _handle_capture_screen(self, arguments: dict[str, Any]) -> list[TextContent]:
        """画面キャプチャを処理"""
        region = arguments.get("region")
        region_tuple = None
        if region:
            region_tuple = (
                region["x"],
                region["y"],
                region["width"],
                region["height"],
            )

        image_data = await self.screen_capture.capture(region_tuple)
        filepath = self._save_capture(image_data, {"action": "capture_screen", "region": region})

        return [TextContent(type="text", text=f"Captured: {filepath}")]

    async def _handle_analyze_screen(self, arguments: dict[str, Any]) -> list[TextContent]:
        """画面分析を処理"""
        prompt = arguments["prompt"]
        level_str = arguments.get("level", "hybrid")
        level = AnalysisLevel(level_str)

        image_data = await self.screen_capture.capture()
        result = await self.analyzer.analyze(image_data, prompt, level=level)

        self._save_capture(
            image_data,
            {"action": "analyze_screen", "prompt": prompt, "level": level_str},
        )

        return [TextContent(type="text", text=result.combined_text)]

    async def _handle_click(self, arguments: dict[str, Any]) -> list[TextContent]:
        """クリックを処理"""
        x = arguments["x"]
        y = arguments["y"]
        double_click = arguments.get("double_click", False)

        await self.action_executor.click(x, y, double_click=double_click)

        return [TextContent(type="text", text=f"Clicked at ({x}, {y})")]

    async def _handle_type_text(self, arguments: dict[str, Any]) -> list[TextContent]:
        """テキスト入力を処理"""
        text = arguments["text"]
        press_enter = arguments.get("press_enter", False)

        await self.action_executor.type_text(text, press_enter=press_enter)

        return [TextContent(type="text", text=f"Typed: {text}")]

    async def _handle_press_key(self, arguments: dict[str, Any]) -> list[TextContent]:
        """キー入力を処理"""
        key = arguments["key"]

        await self.action_executor.press_key(key)

        return [TextContent(type="text", text=f"Pressed: {key}")]

    async def _handle_list_captures(self, arguments: dict[str, Any]) -> list[TextContent]:
        """キャプチャ一覧を処理"""
        json_files = sorted(self.captures_dir.glob("*.json"))

        captures = []
        for f in json_files:
            try:
                data = json.loads(f.read_text())
                captures.append(data)
            except Exception:
                pass

        return [TextContent(type="text", text=json.dumps(captures, indent=2))]

    def _save_capture(
        self,
        image_data: bytes,
        metadata: dict[str, Any],
    ) -> str:
        """キャプチャを保存

        Args:
            image_data: 画像データ
            metadata: メタデータ

        Returns:
            保存したファイルのパス
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")

        # 画像を保存
        image_path = self.captures_dir / f"{timestamp}.png"
        image_path.write_bytes(image_data)

        # メタデータを保存
        meta_path = self.captures_dir / f"{timestamp}.json"
        metadata["timestamp"] = timestamp
        metadata["image_file"] = image_path.name
        meta_path.write_text(json.dumps(metadata, indent=2))

        return str(image_path)

    async def run(self) -> None:
        """サーバーを起動"""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )
