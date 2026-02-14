"""AmbiguityScorer — 曖昧さの定量スコア算出（§5.9 + §8）.

入力テキストから3軸スコア（ambiguity, context_sufficiency, execution_risk）を
ルールベースで算出し、分析パス（Instant Pass / Assumption Pass / Full Analysis）
を決定する。

LLM 非依存の純粋ロジックコンポーネント。
"""

from __future__ import annotations

import re

from colonyforge.requirement_analysis.models import (
    AmbiguityScores,
    AnalysisPath,
)

# ---------------------------------------------------------------------------
# 曖昧語辞書 — ambiguity スコアに寄与する語彙
# ---------------------------------------------------------------------------

#: 曖昧語パターン（日本語）— 主語・目的語・手段が不明確になる表現
_VAGUE_PATTERNS_JA: list[re.Pattern[str]] = [
    re.compile(p)
    for p in [
        r"いい感じ",
        r"適切に",
        r"うまく",
        r"なんとなく",
        r"適当に",
        r"それなりに",
        r"ちゃんと",
        r"きちんと",
        r"しっかり",
        r"良い感じ",
        r"よしなに",
        r"改善",
        r"最適化",
        r"リファクタ",
        r"整理",
        r"見直し",
    ]
]

#: 曖昧語パターン（英語）
_VAGUE_PATTERNS_EN: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bfix\b",
        r"\bimprove\b",
        r"\brefactor\b",
        r"\bclean\s*up\b",
        r"\boptimize\b",
        r"\bbetter\b",
        r"\bsomehow\b",
        r"\bappropriate(?:ly)?\b",
        r"\bproper(?:ly)?\b",
    ]
]

# ---------------------------------------------------------------------------
# 具体性指標 — ambiguity を下げるパターン
# ---------------------------------------------------------------------------

#: 具体性パターン — ファイルパス、コマンド、行番号、URL 等
_CONCRETE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p)
    for p in [
        r"[a-zA-Z_/\\]+\.[a-zA-Z]{1,5}",  # ファイルパス (e.g. src/auth.py)
        r"\d+行",  # 行番号参照
        r"L\d+",  # L42 形式の行番号
        r"pytest|ruff|mypy|git\b",  # 具体的コマンド
        r"https?://",  # URL
        r"`[^`]+`",  # バッククォート内のコード
        r"テスト",  # 日本語: テスト
        r"実行",  # 日本語: 実行
        r"削除",  # 日本語: 削除
        r"作成",  # 日本語: 作成
        r"修正",  # 日本語: 修正（具体的対象あり前提）
        r"追加",  # 日本語: 追加
    ]
]

# ---------------------------------------------------------------------------
# リスクキーワード — execution_risk に寄与する語彙
# ---------------------------------------------------------------------------

#: 高リスクキーワード（セキュリティ、データ、認証等）
_HIGH_RISK_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"認証",
        r"auth",
        r"暗号",
        r"encrypt",
        r"パスワード",
        r"password",
        r"セキュリティ",
        r"security",
        r"決済",
        r"payment",
        r"マイグレーション",
        r"migration",
        r"データベース.*変更",
        r"database.*change",
        r"個人情報",
        r"personal\s*data|pii",
        r"権限",
        r"permission",
        r"トークン",
        r"token",
        r"セッション",
        r"session",
        r"アーキテクチャ",
        r"architecture",
        r"本番",
        r"production",
        r"デプロイ",
        r"deploy",
    ]
]

#: 低リスク指標 — execution_risk を下げるパターン
_LOW_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"README",
        r"ドキュメント|document",
        r"コメント|comment",
        r"タイポ|typo",
        r"テスト.*実行|run.*test",
        r"lint",
        r"フォーマット|format",
        r"バッジ|badge",
    ]
]


class AmbiguityScorer:
    """テキストの曖昧さを定量スコア化する（§5.9 + §8）.

    3軸スコアを算出し、分析パス（Instant Pass / Assumption Pass / Full Analysis）
    を決定する。Phase 1 ではルールベース、Phase 2 で Honeycomb 学習ループにより
    閾値を自動調整する。
    """

    def __init__(
        self,
        *,
        instant_pass_ambiguity: float = 0.3,
        instant_pass_risk: float = 0.3,
        assumption_pass_ambiguity: float = 0.7,
        assumption_pass_risk: float = 0.5,
    ) -> None:
        self.instant_pass_ambiguity = instant_pass_ambiguity
        self.instant_pass_risk = instant_pass_risk
        self.assumption_pass_ambiguity = assumption_pass_ambiguity
        self.assumption_pass_risk = assumption_pass_risk

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def score_text(
        self,
        text: str,
        *,
        context_sufficiency: float | None = None,
    ) -> AmbiguityScores:
        """テキストから AmbiguityScores を算出する.

        Args:
            text: ユーザー入力テキスト
            context_sufficiency: 外部から指定する場合（Context Forager 出力）。
                None の場合はテキスト長に基づく簡易推定値を使用。

        Returns:
            AmbiguityScores
        """
        ambiguity = self._compute_ambiguity(text)
        execution_risk = self._compute_execution_risk(text)

        if context_sufficiency is None:
            context_sufficiency = self._estimate_context_sufficiency(text)

        return AmbiguityScores(
            ambiguity=ambiguity,
            context_sufficiency=context_sufficiency,
            execution_risk=execution_risk,
        )

    def determine_path(self, scores: AmbiguityScores) -> AnalysisPath:
        """AmbiguityScores から分析パスを決定する（§8）.

        判定順序:
        1. Instant Pass: A < instant_pass_ambiguity かつ
           C > (1 - instant_pass_ambiguity) かつ R < instant_pass_risk
        2. Assumption Pass: A < assumption_pass_ambiguity かつ
           R < assumption_pass_risk
        3. Full Analysis: 上記いずれにも該当しない
        """
        # 1. Instant Pass
        if (
            scores.ambiguity < self.instant_pass_ambiguity
            and scores.context_sufficiency > (1.0 - self.instant_pass_ambiguity)
            and scores.execution_risk < self.instant_pass_risk
        ):
            return AnalysisPath.INSTANT_PASS

        # 2. Assumption Pass
        if (
            scores.ambiguity < self.assumption_pass_ambiguity
            and scores.execution_risk < self.assumption_pass_risk
        ):
            return AnalysisPath.ASSUMPTION_PASS

        # 3. Full Analysis
        return AnalysisPath.FULL_ANALYSIS

    def score_and_determine(
        self,
        text: str,
        *,
        context_sufficiency: float | None = None,
    ) -> tuple[AmbiguityScores, AnalysisPath]:
        """テキストからスコア算出 + パス判定を一括実行する.

        Args:
            text: ユーザー入力テキスト
            context_sufficiency: 外部から指定する場合

        Returns:
            (AmbiguityScores, AnalysisPath) のタプル
        """
        scores = self.score_text(text, context_sufficiency=context_sufficiency)
        path = self.determine_path(scores)
        return scores, path

    # ------------------------------------------------------------------
    # private — スコア算出ロジック
    # ------------------------------------------------------------------

    def _compute_ambiguity(self, text: str) -> float:
        """テキストの曖昧さスコアを算出する.

        曖昧語の出現数と具体性指標のバランスで 0.0〜1.0 を返す。
        空テキストは最大曖昧度。
        """
        if not text.strip():
            return 1.0

        # 曖昧語カウント
        vague_count = sum(1 for p in _VAGUE_PATTERNS_JA if p.search(text)) + sum(
            1 for p in _VAGUE_PATTERNS_EN if p.search(text)
        )

        # 具体性カウント
        concrete_count = sum(1 for p in _CONCRETE_PATTERNS if p.search(text))

        # テキスト長による正規化（短すぎるテキストは曖昧寄り）
        length_factor = min(len(text) / 50.0, 1.0)

        # 曖昧度 = 曖昧語の影響 - 具体性の緩和
        # 曖昧語1つにつき +0.2, 具体性1つにつき -0.15
        raw_score = 0.3 + (vague_count * 0.2) - (concrete_count * 0.15)

        # 短いテキストは曖昧寄りに補正（50文字未満）
        if length_factor < 1.0:
            raw_score += (1.0 - length_factor) * 0.2

        return max(0.0, min(1.0, raw_score))

    def _compute_execution_risk(self, text: str) -> float:
        """テキストからの実行リスクスコアを算出する.

        高リスクキーワードと低リスク指標のバランスで算出。
        """
        if not text.strip():
            return 0.5  # 空テキストは中程度リスク

        high_risk_count = sum(1 for p in _HIGH_RISK_KEYWORDS if p.search(text))
        low_risk_count = sum(1 for p in _LOW_RISK_PATTERNS if p.search(text))

        # 高リスクキーワード1つにつき +0.3, 低リスク指標1つにつき -0.15
        raw_score = 0.2 + (high_risk_count * 0.3) - (low_risk_count * 0.15)

        return max(0.0, min(1.0, raw_score))

    def _estimate_context_sufficiency(self, text: str) -> float:
        """テキストベースの context_sufficiency 簡易推定.

        Context Forager（Phase 2）実装前の暫定ロジック。
        テキストが具体的であれば context_sufficiency が高いとみなす。
        """
        if not text.strip():
            return 0.0

        concrete_count = sum(1 for p in _CONCRETE_PATTERNS if p.search(text))
        # 具体性が高いほど「既存情報で足りる」と推定
        return min(0.2 + concrete_count * 0.2, 0.8)
