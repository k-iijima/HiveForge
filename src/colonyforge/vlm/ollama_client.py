"""
Ollama VLMクライアント

ローカルで動作するOllamaのVLM（LLaVA, Qwen-VL等）を呼び出す。
"""

import base64
import logging
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from colonyforge.prompts.vlm import format_screenshot_prompt

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
        """Ollamaが利用可能かチェック

        Returns:
            True: Ollama APIに接続でき、200が返る
            False: 接続失敗（原因はログに出力）
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.ConnectError as exc:
            # ネットワーク接続失敗（Ollama未起動・ホスト不正等）—安全側フォールバック
            logger.debug("Ollama接続失敗 (ConnectError): %s url=%s", exc, self.base_url)
            return False
        except httpx.TimeoutException as exc:
            # タイムアウト
            logger.debug("Ollamaタイムアウト: %s url=%s", exc, self.base_url)
            return False
        except httpx.HTTPError as exc:
            # その他のHTTPエラー
            logger.debug(
                "Ollama HTTPエラー (%s): %s url=%s", type(exc).__name__, exc, self.base_url
            )
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

    # Regex to detect plausible base64-encoded data.
    # Matches strings whose characters are all valid base64 alphabet
    # with optional trailing padding.  Minimum 4 chars (one base64 block).
    _BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{4,}={0,2}$")

    @staticmethod
    def _resolve_image_to_base64(image: bytes | str | Path) -> str:
        """Convert *image* to a base64-encoded string.

        Resolution order:
        1. ``Path`` object → read file, base64-encode.
        2. ``str`` that points to an existing file → same as above.
        3. ``bytes`` → base64-encode.
        4. ``str`` that looks like valid base64 → use as-is.
        5. Otherwise → ``ValueError`` (instead of silently assuming base64).

        Raises:
            ValueError: When a ``str`` is provided that is neither
                an existing file path nor valid base64 data.
        """
        if isinstance(image, Path):
            with open(image, "rb") as f:
                return base64.b64encode(f.read()).decode()

        if isinstance(image, str):
            # Try as file path first — must be a non-empty string
            # pointing to an existing *file* (not directory).
            if image:
                p = Path(image)
                if p.is_file():
                    with open(p, "rb") as f:
                        return base64.b64encode(f.read()).decode()

            # Validate base64 — strip whitespace, then quick pattern check
            stripped = image.strip()
            if OllamaClient._BASE64_RE.match(stripped):
                return stripped

            raise ValueError(
                f"String argument is neither an existing file path "
                f"nor valid base64 data (first 40 chars: {image[:40]!r})"
            )

        if isinstance(image, bytes):
            return base64.b64encode(image).decode()

        raise TypeError(f"Expected bytes, str, or Path; got {type(image).__name__}")

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
        image_b64 = self._resolve_image_to_base64(image)

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
