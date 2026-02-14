"""ハイブリッド分析モジュール

ローカル分析とVLM分析を組み合わせて効率的に画像を分析します。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from colonyforge.vlm_tester.local_analyzers import (
    AnalysisResult,
    LocalAnalyzerPipeline,
)
from colonyforge.vlm_tester.vlm_providers import (
    MultiProviderVLMClient,
    VLMAnalysisResult,
)

logger = logging.getLogger(__name__)

# VLM API呼び出しのタイムアウト（秒）
# AnthropicProvider側にも60秒のタイムアウトがあるが、安全策として設定
VLM_TIMEOUT_SECONDS = 90


class AnalysisLevel(Enum):
    """分析レベル"""

    LOCAL_ONLY = "local_only"  # ローカル分析のみ（高速・無料）
    HYBRID = "hybrid"  # ローカル + 必要時VLM（コスト最適化）
    VLM_OLLAMA = "vlm_ollama"  # ローカルOllama優先
    VLM_CLOUD = "vlm_cloud"  # クラウドVLM（高精度）


@dataclass
class HybridAnalysisResult:
    """ハイブリッド分析結果"""

    analysis_level: AnalysisLevel
    local_results: dict[str, AnalysisResult] = field(default_factory=dict)
    vlm_response: VLMAnalysisResult | None = None
    combined_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class HybridAnalyzer:
    """ハイブリッド分析器

    ローカル分析とVLM分析を組み合わせて画像を分析します。
    - LOCAL_ONLY: OCR/差分分析のみ
    - HYBRID: ローカル分析で不十分な場合にVLMを使用
    - VLM_OLLAMA: ローカルOllamaを優先
    - VLM_CLOUD: クラウドVLM（Anthropic等）を使用
    """

    def __init__(
        self,
        default_level: AnalysisLevel = AnalysisLevel.HYBRID,
        local_pipeline: LocalAnalyzerPipeline | None = None,
        vlm_client: MultiProviderVLMClient | None = None,
    ) -> None:
        """HybridAnalyzerを初期化

        Args:
            default_level: デフォルトの分析レベル
            local_pipeline: ローカル分析パイプライン
            vlm_client: VLMクライアント
        """
        self.default_level = default_level
        self.local_pipeline = local_pipeline or LocalAnalyzerPipeline()
        self.vlm_client = vlm_client or MultiProviderVLMClient()

        # 統計情報
        self._stats = {
            "local_only": 0,
            "vlm_ollama": 0,
            "vlm_cloud": 0,
            "total_requests": 0,
        }

    def get_stats(self) -> dict[str, int]:
        """統計情報を取得"""
        return self._stats.copy()

    async def analyze(
        self,
        image_data: bytes,
        prompt: str,
        *,
        level: AnalysisLevel | None = None,
        previous_image: bytes | None = None,
    ) -> HybridAnalysisResult:
        """画像を分析

        Args:
            image_data: 画像データ
            prompt: 分析プロンプト
            level: 分析レベル（Noneの場合はデフォルト）
            previous_image: 比較用の前回画像

        Returns:
            分析結果
        """
        analysis_level = level or self.default_level
        self._stats["total_requests"] += 1

        # ローカル分析を実行
        local_results = await self.local_pipeline.analyze(
            image_data,
            extract_text=True,
            previous_image=previous_image,
        )

        # LOCAL_ONLYの場合はここで終了
        if analysis_level == AnalysisLevel.LOCAL_ONLY:
            self._stats["local_only"] += 1
            return HybridAnalysisResult(
                analysis_level=analysis_level,
                local_results=local_results,
                vlm_response=None,
                combined_text=self._extract_text_from_local(local_results),
            )

        # VLM分析を実行
        vlm_response = await self._run_vlm_analysis(image_data, prompt, analysis_level)

        # 結果を統合
        combined_text = self._combine_results(local_results, vlm_response)

        return HybridAnalysisResult(
            analysis_level=analysis_level,
            local_results=local_results,
            vlm_response=vlm_response,
            combined_text=combined_text,
        )

    async def _run_vlm_analysis(
        self,
        image_data: bytes,
        prompt: str,
        level: AnalysisLevel,
    ) -> VLMAnalysisResult | None:
        """VLM分析を実行

        VLM API呼び出しにはVLM_TIMEOUT_SECONDSのタイムアウトを設定し、
        タイムアウトまたは例外発生時はNoneを返す。
        """
        import httpx

        coro: Any
        if level == AnalysisLevel.VLM_OLLAMA:
            self._stats["vlm_ollama"] += 1
            coro = self.vlm_client.analyze(image_data, prompt, provider_name="ollama")
        elif level == AnalysisLevel.VLM_CLOUD:
            self._stats["vlm_cloud"] += 1
            coro = self.vlm_client.analyze(image_data, prompt, provider_name="anthropic")
        else:
            # HYBRID: 利用可能なプロバイダーを自動選択
            available = self.vlm_client.get_available_providers()
            if "ollama" in available:
                self._stats["vlm_ollama"] += 1
                coro = self.vlm_client.analyze(image_data, prompt, provider_name="ollama")
            elif "anthropic" in available:
                self._stats["vlm_cloud"] += 1
                coro = self.vlm_client.analyze(image_data, prompt, provider_name="anthropic")
            else:
                return None

        try:
            return await asyncio.wait_for(coro, timeout=VLM_TIMEOUT_SECONDS)
        except TimeoutError:
            # VLM分析はオプショナル: タイムアウト時はローカル結果のみで継続
            logger.warning(
                "VLM分析タイムアウト (level=%s, timeout=%ss)", level.value, VLM_TIMEOUT_SECONDS
            )
            return None
        except httpx.HTTPError as exc:
            # ネットワーク/HTTP エラー: 原因を構造化ログに出力
            logger.warning(
                "VLM分析HTTPエラー (level=%s, %s): %s", level.value, type(exc).__name__, exc
            )
            return None
        except (ValueError, RuntimeError) as exc:
            # プロバイダー設定エラー（APIキー未設定等）
            logger.warning(
                "VLM分析設定エラー (level=%s, %s): %s", level.value, type(exc).__name__, exc
            )
            return None

    def _extract_text_from_local(self, local_results: dict[str, AnalysisResult]) -> str:
        """ローカル分析結果からテキストを抽出"""
        ocr_result = local_results.get("ocr")
        if ocr_result and ocr_result.success:
            return str(ocr_result.data.get("text", ""))
        return ""

    def _combine_results(
        self,
        local_results: dict[str, AnalysisResult],
        vlm_response: VLMAnalysisResult | None,
    ) -> str:
        """ローカル分析とVLM分析の結果を統合"""
        parts: list[str] = []

        # OCRテキスト
        ocr_text = self._extract_text_from_local(local_results)
        if ocr_text:
            parts.append(f"[OCR]\n{ocr_text}")

        # VLMレスポンス
        if vlm_response:
            parts.append(f"[VLM: {vlm_response.provider}]\n{vlm_response.response}")

        return "\n\n".join(parts)
