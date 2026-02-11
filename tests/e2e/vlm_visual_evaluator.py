"""VLM視覚評価ヘルパー

VLM（Vision Language Model）でスクリーンショットを視覚的に評価するヘルパーモジュール。

サポートプロバイダー:
    - Ollama (ローカル): llava:7b 等
    - Anthropic (クラウド): Claude Vision API

環境変数 VLM_PROVIDER で切替可能（デフォルト: 自動検出）。
CI環境では ANTHROPIC_API_KEY を設定して Anthropic プロバイダーを使用する。

2つの評価軸:
    1. VLM構造評価: UIの構造・レイアウト・色・ゲージの視覚的正しさを評価
    2. VLM-OCR評価: 画像内のテキストが正しく読めるかを検証（GLM-OCR的アプローチ）

VLMの非決定論的な応答に対応するため、キーワードマッチングと複数回リトライで
テストの安定性を確保する。

画像品質改善:
    フル画面スクリーンショット(1920x1080等)の中でKPIダッシュボードは小さいため、
    エディタパネル領域をクロップしてからVLMに渡す。
    crop_to_editor_panel() でVS Codeのレイアウトを自動検出しクロップする。
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# VLMプロバイダー設定
# ---------------------------------------------------------------------------
# VLM_PROVIDER: "ollama" | "anthropic" | None (自動検出)
VLM_PROVIDER = os.environ.get("VLM_PROVIDER")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://colonyforge-dev-ollama:11434")
VLM_MODEL = os.environ.get("VLM_MODEL", "llava:7b")


def _get_vlm_client():
    """VLMクライアントを取得する（MultiProviderVLMClient経由）

    VLM_PROVIDER 環境変数でプロバイダーを選択:
        - "ollama": Ollama ローカルサーバー
        - "anthropic": Anthropic Claude Vision API
        - 未設定: 利用可能なプロバイダーを自動検出
    """
    from colonyforge.vlm_tester.vlm_providers import (
        AnthropicProvider,
        MultiProviderVLMClient,
        OllamaProvider,
    )

    providers = [
        OllamaProvider(base_url=OLLAMA_BASE_URL, model=VLM_MODEL),
        AnthropicProvider(),
    ]
    return MultiProviderVLMClient(
        preferred_provider=VLM_PROVIDER,
        providers=providers,
    )


def _check_vlm_available() -> bool:
    """いずれかのVLMプロバイダーが利用可能かチェック"""
    try:
        client = _get_vlm_client()
        available = client.get_available_providers()
        if available:
            logger.info("VLM providers available: %s", available)
            return True
        logger.warning("No VLM provider available")
        return False
    except Exception as e:
        logger.warning("VLM availability check failed: %s", e)
        return False


VLM_AVAILABLE = _check_vlm_available()


# ============================================================
# エディタパネル領域のクロップ
# ============================================================


async def detect_editor_bounds(mcp_client) -> tuple[int, int, int, int] | None:
    """Playwright JS評価でVS Codeのエディタ領域のBounding Boxを検出する

    code-serverのDOM構造を利用してエディタパネルの座標を取得。
    取得できない場合はNoneを返す。

    Returns:
        (x, y, width, height) or None
    """
    js_code = (
        "() => {"
        "  const selectors = ["
        "    '.editor-group-container',"
        "    '.part.editor',"
        "    '.split-view-view .view-container',"
        "    '.editor-container',"
        "  ];"
        "  for (const sel of selectors) {"
        "    const el = document.querySelector(sel);"
        "    if (el) {"
        "      const r = el.getBoundingClientRect();"
        "      if (r.width > 100 && r.height > 100) {"
        "        return JSON.stringify({"
        "          x: Math.round(r.x),"
        "          y: Math.round(r.y),"
        "          w: Math.round(r.width),"
        "          h: Math.round(r.height)"
        "        });"
        "      }"
        "    }"
        "  }"
        "  return 'null';"
        "}"
    )
    try:
        result = await mcp_client._call_tool("browser_evaluate", {"function": js_code})
        import json

        for item in result.content:
            if hasattr(item, "text"):
                # browser_evaluate の結果は "### Result\n\"...\"\n..." 形式
                text = item.text
                for line in text.split("\n"):
                    line = line.strip().strip('"')
                    if line.startswith("{"):
                        data = json.loads(line)
                        return (data["x"], data["y"], data["w"], data["h"])
    except Exception as e:
        logger.debug("Editor bounds detection failed: %s", e)
    return None


def crop_to_editor_panel(
    screenshot_data: bytes,
    editor_bounds: tuple[int, int, int, int] | None = None,
) -> bytes:
    """スクリーンショットからエディタパネル領域をクロップする

    VS Codeのレイアウト:
        [Activity Bar 48px][Sidebar ~300px][Editor Panel][...]
        [                    Status Bar 22px                 ]

    editor_bounds が指定されている場合はそれを使用し、
    なければヒューリスティックに推定する。

    Args:
        screenshot_data: フルスクリーンショットのPNGデータ
        editor_bounds: (x, y, width, height) JS評価で取得した値

    Returns:
        クロップされたPNGデータ
    """
    from PIL import Image

    img = Image.open(io.BytesIO(screenshot_data))
    w, h = img.size

    if editor_bounds:
        x, y, ew, eh = editor_bounds
        # Bounding Boxでクロップ（少し広めに取る）
        left = max(0, x - 5)
        top = max(0, y - 5)
        right = min(w, x + ew + 5)
        bottom = min(h, y + eh + 5)
    else:
        # ヒューリスティック: Activity Bar(48px) + Sidebar(~300px) を除外
        # Status bar(22px) を下から除外
        left = min(int(w * 0.25), 350)  # サイドバーの右端（幅の25%か350pxの小さい方）
        top = 0
        right = w
        bottom = max(0, h - 22)  # ステータスバーを除外

    cropped = img.crop((left, top, right, bottom))

    # クロップ後のサイズをログ
    logger.info(
        "Cropped screenshot: %dx%d -> %dx%d (bounds=%s)",
        w,
        h,
        cropped.size[0],
        cropped.size[1],
        editor_bounds,
    )

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


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
    vlm_client = _get_vlm_client()
    threshold = min_keywords if min_keywords is not None else len(expected_keywords)

    best_result: VLMEvalResult | None = None

    for attempt in range(retries):
        try:
            vlm_response = await vlm_client.analyze(image_data, prompt)
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
                "VLM eval attempt %d/%d: found %d/%d keywords (provider=%s)",
                attempt + 1,
                retries,
                len(found),
                threshold,
                vlm_response.provider,
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
    vlm_client = _get_vlm_client()

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
            vlm_response = await vlm_client.analyze(image_data, ocr_prompt)
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
    vlm_client = _get_vlm_client()
    vlm_response = await vlm_client.analyze(image_data, question)
    return vlm_response.response.strip()
