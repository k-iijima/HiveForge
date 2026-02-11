"""VLM視覚評価ヘルパー

Playwright MCPでキャプチャしたスクリーンショットをOllama VLM (llava:7b) で
視覚的に評価するためのヘルパーモジュール。

2つの評価軸:
    1. VLM構造評価: UIの構造・レイアウト・色・ゲージの視覚的正しさを評価
    2. VLM-OCR評価: 画像内のテキストが正しく読めるかを検証（GLM-OCR的アプローチ）

VLMの非決定論的な応答に対応するため、キーワードマッチングと複数回リトライで
テストの安定性を確保する。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://hiveforge-dev-ollama:11434")
VLM_MODEL = os.environ.get("VLM_MODEL", "llava:7b")


def _check_ollama_available() -> bool:
    """OllamaサーバーへのTCP接続チェック"""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(OLLAMA_BASE_URL)
    host = parsed.hostname or "hiveforge-dev-ollama"
    port = parsed.port or 11434
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


OLLAMA_AVAILABLE = _check_ollama_available()


@dataclass
class VLMEvalResult:
    """VLM評価結果"""

    question: str
    raw_response: str
    keywords_found: list[str] = field(default_factory=list)
    keywords_missing: list[str] = field(default_factory=list)
    success: bool = False

    def __str__(self) -> str:
        status = "PASS" if self.success else "FAIL"
        return (
            f"[{status}] {self.question}\n"
            f"  Found: {self.keywords_found}\n"
            f"  Missing: {self.keywords_missing}\n"
            f"  Response (first 200): {self.raw_response[:200]}"
        )


async def vlm_evaluate(
    image_data: bytes,
    prompt: str,
    expected_keywords: list[str],
    *,
    min_keywords: int | None = None,
    model: str | None = None,
    retries: int = 2,
) -> VLMEvalResult:
    """VLMに画像を渡して応答をキーワード評価する

    Args:
        image_data: PNG画像データ
        prompt: VLMへの質問プロンプト
        expected_keywords: 応答に含まれるべきキーワード（大文字小文字無視）
        min_keywords: 最低限見つかるべきキーワード数（None=全て必須）
        model: 使用するVLMモデル
        retries: リトライ回数（VLMの非決定性対策）

    Returns:
        VLMEvalResult: 評価結果
    """
    from hiveforge.vlm.ollama_client import OllamaClient

    client = OllamaClient(base_url=OLLAMA_BASE_URL, model=model or VLM_MODEL, timeout=120)
    threshold = min_keywords if min_keywords is not None else len(expected_keywords)

    best_result: VLMEvalResult | None = None

    for attempt in range(retries):
        try:
            vlm_response = await client.analyze_image(image_data, prompt)
            response_lower = vlm_response.response.lower()

            found = [kw for kw in expected_keywords if kw.lower() in response_lower]
            missing = [kw for kw in expected_keywords if kw.lower() not in response_lower]

            result = VLMEvalResult(
                question=prompt[:100],
                raw_response=vlm_response.response,
                keywords_found=found,
                keywords_missing=missing,
                success=len(found) >= threshold,
            )

            if result.success:
                return result

            # 最良の結果を保持
            if best_result is None or len(result.keywords_found) > len(best_result.keywords_found):
                best_result = result

            logger.info(
                "VLM eval attempt %d/%d: found %d/%d keywords",
                attempt + 1,
                retries,
                len(found),
                threshold,
            )

        except Exception as e:
            logger.warning("VLM eval attempt %d failed: %s", attempt + 1, e)
            if best_result is None:
                best_result = VLMEvalResult(
                    question=prompt[:100],
                    raw_response=f"ERROR: {e}",
                    success=False,
                )

    return best_result  # type: ignore[return-value]


async def vlm_ocr_extract(
    image_data: bytes,
    *,
    model: str | None = None,
    retries: int = 2,
) -> str:
    """VLMを使って画像内のテキストをOCR的に抽出する（GLM-OCR的アプローチ）

    専用OCRモデルではなくVLMの視覚的テキスト認識能力を活用する。
    llava:7bは画像内のテキストを高精度に読み取れる。

    Args:
        image_data: PNG画像データ
        model: 使用するVLMモデル
        retries: リトライ回数

    Returns:
        抽出されたテキスト
    """
    from hiveforge.vlm.ollama_client import OllamaClient

    client = OllamaClient(base_url=OLLAMA_BASE_URL, model=model or VLM_MODEL, timeout=120)

    # OCR特化プロンプト: テキストのみを正確に読み取るよう指示
    ocr_prompt = (
        "Read ALL text visible in this screenshot. "
        "Output ONLY the text you can see, preserving the layout as much as possible. "
        "Include numbers, percentages, labels, headings, and any other visible text. "
        "Do not describe the image or add any commentary. "
        "Just output the raw text content."
    )

    best_text = ""

    for attempt in range(retries):
        try:
            vlm_response = await client.analyze_image(image_data, ocr_prompt)
            text = vlm_response.response.strip()

            # よりテキストが多い応答を採用
            if len(text) > len(best_text):
                best_text = text

            # 十分な量のテキストが抽出できたら早期return
            if len(text) > 100:
                return text

        except Exception as e:
            logger.warning("VLM OCR attempt %d failed: %s", attempt + 1, e)

    return best_text


async def vlm_visual_qa(
    image_data: bytes,
    question: str,
    *,
    model: str | None = None,
) -> str:
    """VLMに画像と質問を渡して回答を得る（汎用QA）

    Args:
        image_data: PNG画像データ
        question: 質問テキスト
        model: 使用するVLMモデル

    Returns:
        VLMの応答テキスト
    """
    from hiveforge.vlm.ollama_client import OllamaClient

    client = OllamaClient(base_url=OLLAMA_BASE_URL, model=model or VLM_MODEL, timeout=120)
    vlm_response = await client.analyze_image(image_data, question)
    return vlm_response.response.strip()
