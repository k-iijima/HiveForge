"""
ローカルVLM解析器

Playwright MCPのスクリーンショットをローカルVLMで解析する。
"""

import asyncio
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from .ollama_client import OllamaClient, VLMResponse


class AnalysisResult(BaseModel):
    """UI解析結果"""

    screenshot_path: Optional[str] = None
    analysis: str = Field(..., description="VLM解析結果テキスト")
    model: str = Field(..., description="使用したモデル")
    duration_ms: int = Field(0, description="解析時間（ミリ秒）")
    elements_found: list[str] = Field(default_factory=list, description="検出されたUI要素")


class LocalVLMAnalyzer:
    """ローカルVLMを使用したUI解析器

    公式Playwright MCPと組み合わせて使用：
    1. Playwright MCPでスクリーンショット取得
    2. LocalVLMAnalyzerでローカル解析（コスト無料）
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "llava:7b",
    ):
        self.client = OllamaClient(base_url=ollama_url, model=model)

    async def is_ready(self) -> bool:
        """VLM解析が準備完了かチェック"""
        if not await self.client.is_available():
            return False
        models = await self.client.list_models()
        return self.client.model in models

    async def setup(self) -> bool:
        """VLM環境をセットアップ（モデルダウンロード含む）"""
        if not await self.client.is_available():
            raise RuntimeError(
                "Ollama is not running. Start with: docker compose -f docker-compose.vlm.yml up -d"
            )

        models = await self.client.list_models()
        if self.client.model not in models:
            print(f"Downloading {self.client.model}...")
            return await self.client.pull_model()
        return True

    async def analyze(
        self,
        image: bytes | str | Path,
        prompt: Optional[str] = None,
    ) -> AnalysisResult:
        """画像を解析

        Args:
            image: 画像データまたはファイルパス
            prompt: カスタムプロンプト（省略時はUI解析用）

        Returns:
            AnalysisResult: 解析結果
        """
        if prompt:
            response = await self.client.analyze_image(image, prompt)
        else:
            response = await self.client.analyze_screenshot(image)

        # UI要素を抽出（簡易的）
        elements = self._extract_elements(response.response)

        return AnalysisResult(
            screenshot_path=str(image) if isinstance(image, (str, Path)) else None,
            analysis=response.response,
            model=response.model,
            duration_ms=response.total_duration_ms,
            elements_found=elements,
        )

    def _extract_elements(self, text: str) -> list[str]:
        """解析結果からUI要素を抽出"""
        elements = []
        keywords = [
            "sidebar",
            "editor",
            "panel",
            "button",
            "menu",
            "tab",
            "toolbar",
            "status bar",
            "activity bar",
            "explorer",
            "terminal",
            "output",
            "problems",
            "debug",
            "extensions",
            "search",
            "source control",
            "notifications",
        ]
        text_lower = text.lower()
        for keyword in keywords:
            if keyword in text_lower:
                elements.append(keyword)
        return elements

    async def compare_screenshots(
        self,
        before: bytes | str | Path,
        after: bytes | str | Path,
    ) -> str:
        """2つのスクリーンショットを比較"""
        # 個別に解析して差分を検出
        before_result = await self.analyze(before)
        after_result = await self.analyze(after)

        prompt = f"""Compare these two UI states:

BEFORE:
{before_result.analysis}

AFTER:
{after_result.analysis}

What changed between these two states? List the differences."""

        # afterの画像で差分分析
        response = await self.client.analyze_image(after, prompt)
        return response.response


# 便利なユーティリティ関数
async def analyze_with_local_vlm(
    image: bytes | str | Path,
    ollama_url: str = "http://localhost:11434",
    model: str = "llava:7b",
) -> AnalysisResult:
    """ワンショットでローカルVLM解析を実行"""
    analyzer = LocalVLMAnalyzer(ollama_url=ollama_url, model=model)
    return await analyzer.analyze(image)
