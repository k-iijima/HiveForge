"""Agent UI ハンドラー

各ツールの実装ロジック。
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import ImageContent, TextContent

from hiveforge.vlm_tester.hybrid_analyzer import AnalysisLevel, HybridAnalyzer
from hiveforge.vlm_tester.local_analyzers import DiffAnalyzer

if TYPE_CHECKING:
    from .session import BrowserSession


class AgentUIHandlers:
    """Agent UI ハンドラー

    ブラウザ操作・分析ツールの実装。
    """

    def __init__(
        self,
        session: BrowserSession,
        captures_dir: Path,
        analyzer: HybridAnalyzer | None = None,
        diff_analyzer: DiffAnalyzer | None = None,
    ) -> None:
        self.session = session
        self.captures_dir = captures_dir
        self.analyzer = analyzer or HybridAnalyzer()
        self.diff_analyzer = diff_analyzer or DiffAnalyzer()
        self._last_capture: bytes | None = None

    async def handle_navigate(self, args: dict[str, Any]) -> list[TextContent]:
        """URLに移動"""
        await self.session.ensure_browser()
        url = args["url"]
        await self.session.navigate(url)
        return [TextContent(type="text", text=f"Navigated to: {url} (via MCP)")]

    async def handle_capture_screen(self, args: dict[str, Any]) -> list[TextContent | ImageContent]:
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

    async def handle_describe_page(self, args: dict[str, Any]) -> list[TextContent | ImageContent]:
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

    async def handle_find_element(self, args: dict[str, Any]) -> list[TextContent]:
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

    async def handle_compare(self, args: dict[str, Any]) -> list[TextContent | ImageContent]:
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

    async def handle_click(self, args: dict[str, Any]) -> list[TextContent]:
        """クリック"""
        await self.session.ensure_browser()

        x = args.get("x")
        y = args.get("y")
        element = args.get("element")
        double_click = args.get("double_click", False)

        # 要素指定の場合はfind_elementで座標を取得
        if element and (x is None or y is None):
            find_result = await self.handle_find_element({"description": element})
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

    async def handle_type_text(self, args: dict[str, Any]) -> list[TextContent]:
        """テキスト入力"""
        await self.session.ensure_browser()

        text = args["text"]
        press_enter = args.get("press_enter", False)

        await self.session.executor.type_text(text, press_enter=press_enter)

        msg = f"入力しました: {text}"
        if press_enter:
            msg += " (Enter押下)"
        return [TextContent(type="text", text=msg)]

    async def handle_press_key(self, args: dict[str, Any]) -> list[TextContent]:
        """キー入力"""
        await self.session.ensure_browser()

        key = args["key"]
        await self.session.executor.press_key(key)

        return [TextContent(type="text", text=f"キーを押しました: {key}")]

    async def handle_scroll(self, args: dict[str, Any]) -> list[TextContent]:
        """スクロール"""
        await self.session.ensure_browser()

        direction = args["direction"]
        amount = args.get("amount", 300)

        # ページ中央でスクロール（MCPモードではデフォルト値を使用）
        x = 400
        y = 300

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

    async def handle_wait_for_element(self, args: dict[str, Any]) -> list[TextContent]:
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

            find_result = await self.handle_find_element({"description": description})
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

    async def handle_close_browser(self, args: dict[str, Any]) -> list[TextContent]:
        """ブラウザを閉じる"""
        await self.session.close()
        return [TextContent(type="text", text="ブラウザを閉じました")]

    async def handle_list_captures(self, args: dict[str, Any]) -> list[TextContent]:
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
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")

        image_path = self.captures_dir / f"{timestamp}.png"
        image_path.write_bytes(image_data)

        meta_path = self.captures_dir / f"{timestamp}.json"
        metadata["timestamp"] = timestamp
        metadata["image_file"] = image_path.name
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        return str(image_path)
