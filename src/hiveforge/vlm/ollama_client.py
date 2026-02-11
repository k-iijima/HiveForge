"""
Ollama VLMクライアント

ローカルで動作するOllamaのVLM（LLaVA, Qwen-VL等）を呼び出す。
"""

import base64
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from hiveforge.prompts.vlm import format_screenshot_prompt

logger = logging.getLogger(__name__)


class VLMResponse(BaseModel):
    """VLM解析結果"""

    response: str = Field(..., description="VLMからのテキスト応答")
    model: str = Field(..., description="使用したモデル名")
    prompt_tokens: int = Field(0, description="プロンプトのトークン数")
    response_tokens: int = Field(0, description="応答のトークン数")
    total_duration_ms: int = Field(0, description="処理時間（ミリ秒）")


class OllamaClient:
    """Ollama VLMクライアント"""

    DEFAULT_MODELS = [
        "llava:7b",  # 汎用VLM（推奨）
        "llava:13b",  # より高精度
        "qwen2.5-vl:7b",  # Qwen VL
        "minicpm-v:latest",  # 軽量VLM
    ]

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llava:7b",
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def is_available(self) -> bool:
        """Ollamaが利用可能かチェック"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError as e:
            # ネットワーク接続失敗は「利用不可」として返す（安全側フォールバック）
            logger.debug("Ollama is not available: %s", e)
            return False

    async def list_models(self) -> list[str]:
        """インストール済みモデル一覧を取得"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except httpx.HTTPError as e:
            logger.warning("Failed to list Ollama models: %s", e)
            raise

    async def pull_model(self, model: str | None = None) -> bool:
        """モデルをダウンロード"""
        model = model or self.model
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model, "stream": False},
                )
                return response.status_code == 200
        except httpx.HTTPError as e:
            logger.error("Failed to pull Ollama model %s: %s", model, e)
            raise

    async def analyze_image(
        self,
        image: bytes | str | Path,
        prompt: str,
        model: str | None = None,
    ) -> VLMResponse:
        """画像をVLMで解析

        Args:
            image: 画像データ（bytes, base64文字列, またはファイルパス）
            prompt: 解析プロンプト
            model: 使用するモデル（省略時はデフォルト）

        Returns:
            VLMResponse: 解析結果
        """
        model = model or self.model

        # 画像をbase64に変換
        if isinstance(image, Path) or (isinstance(image, str) and Path(image).exists()):
            with open(image, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()
        elif isinstance(image, bytes):
            image_b64 = base64.b64encode(image).decode()
        else:
            # すでにbase64文字列と仮定
            image_b64 = image

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()

        return VLMResponse(
            response=data.get("response", ""),
            model=model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            response_tokens=data.get("eval_count", 0),
            total_duration_ms=data.get("total_duration", 0) // 1_000_000,
        )

    async def analyze_screenshot(
        self,
        image: bytes | str | Path,
        context: str = "",
    ) -> VLMResponse:
        """スクリーンショットをUI解析用プロンプトで解析

        Args:
            image: スクリーンショット画像
            context: 追加コンテキスト（任意）

        Returns:
            VLMResponse: UI解析結果
        """
        prompt = format_screenshot_prompt(context)

        return await self.analyze_image(image, prompt)
