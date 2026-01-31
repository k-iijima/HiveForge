"""ローカル分析モジュール

VLMを使用せずにローカルで画像を分析するためのツールを提供します。
- OCR: 画像からテキストを抽出
- Diff: 画像の差分を検出
"""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisResult:
    """分析結果"""

    analyzer: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class OCRAnalyzer:
    """OCR分析器

    EasyOCRまたはTesseractを使用してテキストを抽出します。
    """

    def __init__(self, engine: str | None = None) -> None:
        """OCRAnalyzerを初期化

        Args:
            engine: 使用するOCRエンジン（"easyocr", "tesseract", または None で自動検出）
        """
        self.engine = engine or self._detect_engine()

    def _detect_engine(self) -> str:
        """利用可能なOCRエンジンを検出"""
        # EasyOCRを優先
        if "easyocr" in sys.modules or self._try_import("easyocr"):
            return "easyocr"

        # Tesseractをフォールバック
        if "pytesseract" in sys.modules or self._try_import("pytesseract"):
            return "tesseract"

        return "none"

    def _try_import(self, module_name: str) -> bool:
        """モジュールがインポート可能かテスト"""
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    async def extract_text(self, image_data: bytes) -> AnalysisResult:
        """画像からテキストを抽出

        Args:
            image_data: 画像データ（PNG）

        Returns:
            抽出結果
        """
        if self.engine == "none":
            return AnalysisResult(
                analyzer="ocr",
                success=False,
                error="No OCR engine available",
            )

        try:
            if self.engine == "easyocr":
                text = await self._extract_with_easyocr(image_data)
            else:
                text = await self._extract_with_tesseract(image_data)

            return AnalysisResult(
                analyzer="ocr",
                success=True,
                data={"text": text},
            )
        except Exception as e:
            return AnalysisResult(
                analyzer="ocr",
                success=False,
                error=str(e),
            )

    async def _extract_with_easyocr(self, image_data: bytes) -> str:
        """EasyOCRでテキスト抽出"""
        import easyocr  # type: ignore
        from PIL import Image

        image = Image.open(io.BytesIO(image_data))

        reader = easyocr.Reader(["en", "ja"])
        results = reader.readtext(image)

        # テキストを結合
        texts = [result[1] for result in results]
        return "\n".join(texts)

    async def _extract_with_tesseract(self, image_data: bytes) -> str:
        """Tesseractでテキスト抽出"""
        import pytesseract  # type: ignore
        from PIL import Image

        image = Image.open(io.BytesIO(image_data))
        text = pytesseract.image_to_string(image, lang="eng+jpn")
        return text


class DiffAnalyzer:
    """画像差分分析器

    2つの画像を比較して差分を検出します。
    """

    def __init__(self, threshold: float = 0.01) -> None:
        """DiffAnalyzerを初期化

        Args:
            threshold: 差分と判定するしきい値（0.0〜1.0）
        """
        self.threshold = threshold

    async def compare(
        self,
        image1: bytes,
        image2: bytes,
    ) -> AnalysisResult:
        """2つの画像を比較

        Args:
            image1: 1つ目の画像データ
            image2: 2つ目の画像データ

        Returns:
            比較結果
        """
        try:
            from PIL import Image
            import numpy as np

            img1 = Image.open(io.BytesIO(image1)).convert("RGB")
            img2 = Image.open(io.BytesIO(image2)).convert("RGB")

            # サイズが異なる場合はリサイズ
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)

            # NumPy配列に変換
            arr1 = np.array(img1, dtype=np.float32)
            arr2 = np.array(img2, dtype=np.float32)

            # 差分を計算
            diff = np.abs(arr1 - arr2)
            diff_ratio = np.mean(diff) / 255.0

            is_same = bool(diff_ratio < self.threshold)

            return AnalysisResult(
                analyzer="diff",
                success=True,
                data={
                    "is_same": is_same,
                    "diff_ratio": float(diff_ratio),
                    "threshold": self.threshold,
                },
            )
        except Exception as e:
            return AnalysisResult(
                analyzer="diff",
                success=False,
                error=str(e),
            )

    async def create_diff_image(
        self,
        image1: bytes,
        image2: bytes,
    ) -> bytes | None:
        """差分画像を作成

        Args:
            image1: 1つ目の画像データ
            image2: 2つ目の画像データ

        Returns:
            差分画像（PNG）。エラーの場合はNone
        """
        try:
            from PIL import Image, ImageChops

            img1 = Image.open(io.BytesIO(image1)).convert("RGB")
            img2 = Image.open(io.BytesIO(image2)).convert("RGB")

            # サイズが異なる場合はリサイズ
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)

            # 差分画像を作成
            diff = ImageChops.difference(img1, img2)

            buffer = io.BytesIO()
            diff.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception:
            return None


class LocalAnalyzerPipeline:
    """ローカル分析パイプライン

    複数のローカル分析器を組み合わせて分析を行います。
    """

    def __init__(
        self,
        ocr_analyzer: OCRAnalyzer | None = None,
        diff_analyzer: DiffAnalyzer | None = None,
    ) -> None:
        """LocalAnalyzerPipelineを初期化

        Args:
            ocr_analyzer: OCR分析器
            diff_analyzer: 差分分析器
        """
        self.ocr = ocr_analyzer or OCRAnalyzer()
        self.diff = diff_analyzer or DiffAnalyzer()

    async def analyze(
        self,
        image_data: bytes,
        *,
        extract_text: bool = True,
        previous_image: bytes | None = None,
    ) -> dict[str, AnalysisResult]:
        """画像を分析

        Args:
            image_data: 画像データ
            extract_text: テキスト抽出を行うかどうか
            previous_image: 比較用の前回画像

        Returns:
            分析結果の辞書
        """
        results: dict[str, AnalysisResult] = {}

        if extract_text:
            results["ocr"] = await self.ocr.extract_text(image_data)

        if previous_image:
            results["diff"] = await self.diff.compare(previous_image, image_data)

        return results
