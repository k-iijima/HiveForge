"""VLMプロバイダーモジュール

複数のVLMプロバイダー（Ollama、Anthropic等）をサポートします。
"""

from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class VLMAnalysisResult:
    """VLM分析結果"""

    response: str
    provider: str
    model: str
    raw_response: dict[str, Any] | None = None


class VLMProvider(ABC):
    """VLMプロバイダーの基底クラス"""

    @property
    @abstractmethod
    def name(self) -> str:
        """プロバイダー名を返す"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """プロバイダーが利用可能かどうかを返す"""
        ...

    @abstractmethod
    async def analyze(self, image_data: bytes, prompt: str) -> VLMAnalysisResult:
        """画像を分析する"""
        ...


class OllamaProvider(VLMProvider):
    """Ollamaプロバイダー

    ローカルで動作するOllamaを使用してVLM分析を行います。
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        """OllamaProviderを初期化

        Args:
            base_url: OllamaのベースURL
            model: 使用するモデル名
        """
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "llava:7b")

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Ollamaが利用可能かどうかを確認"""
        import httpx

        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def analyze(self, image_data: bytes, prompt: str) -> VLMAnalysisResult:
        """Ollamaで画像を分析"""
        import httpx

        image_base64 = base64.b64encode(image_data).decode("utf-8")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [image_base64],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()

        return VLMAnalysisResult(
            response=data.get("response", ""),
            provider=self.name,
            model=self.model,
            raw_response=data,
        )


class AnthropicProvider(VLMProvider):
    """Anthropicプロバイダー

    Claude APIを使用してVLM分析を行います。
    """

    def __init__(self, model: str | None = None) -> None:
        """AnthropicProviderを初期化

        Args:
            model: 使用するモデル名
        """
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._api_key: str | None = None

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def api_key(self) -> str | None:
        """APIキーを取得"""
        if self._api_key is None:
            self._api_key = os.environ.get("ANTHROPIC_API_KEY")
        return self._api_key

    def is_available(self) -> bool:
        """AnthropicのAPIキーが設定されているかどうかを確認"""
        return self.api_key is not None

    async def analyze(self, image_data: bytes, prompt: str) -> VLMAnalysisResult:
        """Anthropic Claudeで画像を分析

        AsyncAnthropicクライアントを使用し、タイムアウト60秒を設定。
        """
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

        import anthropic  # type: ignore[import-not-found]

        image_base64 = base64.b64encode(image_data).decode("utf-8")

        client = anthropic.AsyncAnthropic(
            api_key=self.api_key,
            timeout=60.0,
        )

        message = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        response_text = ""
        for block in message.content:
            if hasattr(block, "text"):
                response_text += block.text

        return VLMAnalysisResult(
            response=response_text,
            provider=self.name,
            model=self.model,
            raw_response=None,  # Anthropic SDKのレスポンスは辞書ではない
        )


class MultiProviderVLMClient:
    """マルチプロバイダーVLMクライアント

    複数のVLMプロバイダーを管理し、利用可能なプロバイダーを選択します。
    """

    def __init__(
        self,
        preferred_provider: str | None = None,
        providers: list[VLMProvider] | None = None,
    ) -> None:
        """MultiProviderVLMClientを初期化

        Args:
            preferred_provider: 優先プロバイダー名
            providers: プロバイダーのリスト
        """
        self.preferred_provider = preferred_provider
        self._providers: list[VLMProvider] = providers or [
            OllamaProvider(),
            AnthropicProvider(),
        ]

    def get_available_providers(self) -> list[str]:
        """利用可能なプロバイダーのリストを返す"""
        return [p.name for p in self._providers if p.is_available()]

    def get_provider(self, name: str | None = None) -> VLMProvider | None:
        """指定された名前のプロバイダーを取得

        Args:
            name: プロバイダー名。Noneの場合は優先プロバイダーまたは最初の利用可能なプロバイダー

        Returns:
            プロバイダー。見つからない場合はNone
        """
        target_name = name or self.preferred_provider

        if target_name:
            for p in self._providers:
                if p.name == target_name and p.is_available():
                    return p

        # 優先プロバイダーが見つからない場合は最初の利用可能なプロバイダー
        for p in self._providers:
            if p.is_available():
                return p

        return None

    async def analyze(
        self,
        image_data: bytes,
        prompt: str,
        provider_name: str | None = None,
    ) -> VLMAnalysisResult:
        """画像を分析

        Args:
            image_data: 画像データ（PNG）
            prompt: プロンプト
            provider_name: 使用するプロバイダー名

        Returns:
            分析結果

        Raises:
            RuntimeError: 利用可能なプロバイダーがない場合
        """
        provider = self.get_provider(provider_name)

        if provider is None:
            raise RuntimeError("No VLM provider available")

        return await provider.analyze(image_data, prompt)
