"""VLMクライアントモジュール

Anthropic Claude APIを使用した画像分析クライアント。
"""

from __future__ import annotations

import base64
import os
from typing import Any


class VLMClient:
    """VLMクライアント

    Anthropic Claude APIを使用して画像を分析します。
    """

    def __init__(self, model: str | None = None) -> None:
        """VLMClientを初期化

        Args:
            model: 使用するモデル名
        """
        self.model = model or os.environ.get("VLM_MODEL") or "claude-sonnet-4-20250514"
        self._client: Any = None

    def _get_client(self) -> Any:
        """Anthropicクライアントを取得

        Returns:
            Anthropicクライアント

        Raises:
            RuntimeError: APIキーが設定されていない場合
        """
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

            import anthropic  # type: ignore[import-not-found]

            self._client = anthropic.Anthropic(api_key=api_key)

        return self._client

    async def analyze(
        self,
        image_data: bytes,
        prompt: str,
    ) -> str:
        """画像を分析

        Args:
            image_data: 画像データ（PNG）
            prompt: 分析プロンプト

        Returns:
            分析結果のテキスト
        """
        client = self._get_client()

        image_base64 = base64.b64encode(image_data).decode("utf-8")

        message = client.messages.create(
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

        # レスポンスからテキストを抽出
        response_text = ""
        for block in message.content:
            if hasattr(block, "text"):
                response_text += block.text

        return response_text
