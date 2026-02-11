"""Referee Bee データモデル

N案候補の多面的自動採点・生存選抜のためのデータモデル。

5指標:
- Correctness: 仕様適合テスト合格率
- Robustness: 変異テスト耐性 + 境界値テスト合格率
- Consistency: 差分実行一致性
- Security: 静的解析ルール違反数
- Latency: ベンチマーク実行時間（相対比較）
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScoringDimension(StrEnum):
    """スコアリング指標（コンセプトv6より）"""

    CORRECTNESS = "correctness"
    ROBUSTNESS = "robustness"
    CONSISTENCY = "consistency"
    SECURITY = "security"
    LATENCY = "latency"


class RefereeVerdict(StrEnum):
    """Referee判定

    - SELECTED: 上位K件を選抜
    - SINGLE_PASS: 単一候補（Refereeスキップ）
    - NO_CANDIDATE: 候補なし
    """

    SELECTED = "selected"
    SINGLE_PASS = "single_pass"
    NO_CANDIDATE = "no_candidate"


class ScoreWeights(BaseModel):
    """スコア重み付け

    FinalScore = 0.40×Correctness + 0.20×Robustness
               + 0.20×Consistency + 0.10×Security + 0.10×Latency
    """

    model_config = ConfigDict(strict=True, frozen=True)

    correctness: float = Field(default=0.40, ge=0.0, le=1.0)
    robustness: float = Field(default=0.20, ge=0.0, le=1.0)
    consistency: float = Field(default=0.20, ge=0.0, le=1.0)
    security: float = Field(default=0.10, ge=0.0, le=1.0)
    latency: float = Field(default=0.10, ge=0.0, le=1.0)


class CandidateScore(BaseModel):
    """候補スコア（5次元）"""

    model_config = ConfigDict(strict=True, frozen=True)

    candidate_id: str = Field(..., description="候補ID")
    correctness: float = Field(default=0.0, ge=0.0, le=1.0, description="仕様適合率")
    robustness: float = Field(default=0.0, ge=0.0, le=1.0, description="変異テスト耐性")
    consistency: float = Field(default=0.0, ge=0.0, le=1.0, description="差分一致率")
    security: float = Field(default=0.0, ge=0.0, le=1.0, description="セキュリティスコア")
    latency: float = Field(default=0.0, ge=0.0, le=1.0, description="レイテンシスコア")

    def final_score(self, weights: ScoreWeights | None = None) -> float:
        """重み付き最終スコアを計算"""
        w = weights or ScoreWeights()
        return (
            w.correctness * self.correctness
            + w.robustness * self.robustness
            + w.consistency * self.consistency
            + w.security * self.security
            + w.latency * self.latency
        )


class DiffResult(BaseModel):
    """Differential Testing結果"""

    model_config = ConfigDict(strict=True, frozen=True)

    candidate_a: str = Field(..., description="候補A ID")
    candidate_b: str = Field(..., description="候補B ID")
    input_description: str = Field(..., description="入力の説明")
    outputs_match: bool = Field(..., description="出力が一致するか")
    diff_details: dict[str, Any] = Field(default_factory=dict, description="差分詳細")


class SelectionResult(BaseModel):
    """トーナメント選抜結果"""

    model_config = ConfigDict(strict=True, frozen=True)

    selected_ids: list[str] = Field(..., description="選抜された候補ID")
    rankings: list[CandidateScore] = Field(
        default_factory=list, description="スコア降順の全候補ランキング"
    )
    reason: str = Field(default="", description="選抜理由")


class RefereeReport(BaseModel):
    """Referee Beeレポート

    Guard Beeに渡す最終レポート。
    """

    model_config = ConfigDict(strict=True)

    run_id: str = Field(..., description="Run ID")
    colony_id: str = Field(..., description="Colony ID")
    candidate_count: int = Field(default=0, ge=0, description="候補数")
    selected_ids: list[str] = Field(default_factory=list, description="選抜候補ID")
    scores: list[CandidateScore] = Field(default_factory=list, description="全候補スコア")
    diff_results: list[DiffResult] = Field(
        default_factory=list, description="Differential Testing結果"
    )
    verdict: RefereeVerdict = Field(default=RefereeVerdict.NO_CANDIDATE, description="判定")

    def summary(self) -> dict[str, Any]:
        """レポートサマリー"""
        return {
            "candidate_count": self.candidate_count,
            "selected_count": len(self.selected_ids),
            "verdict": self.verdict.value,
        }
