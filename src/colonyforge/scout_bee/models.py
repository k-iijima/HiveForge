"""Scout Bee データモデル

テンプレート統計、最適化提案、Scout Beeレポートの定義。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ScoutVerdict(StrEnum):
    """Scout Beeの判定結果"""

    RECOMMENDED = "recommended"
    COLD_START = "cold_start"
    INSUFFICIENT_DATA = "insufficient_data"


class TemplateStats(BaseModel):
    """テンプレート別の統計情報"""

    model_config = ConfigDict(frozen=True)

    template_name: str = Field(..., description="テンプレート名")
    total_count: int = Field(default=0, description="総エピソード数")
    success_count: int = Field(default=0, description="成功エピソード数")
    success_rate: float = Field(default=0.0, description="成功率", ge=0.0, le=1.0)
    avg_duration_seconds: float = Field(default=0.0, description="平均所要時間（秒）", ge=0.0)


class OptimizationProposal(BaseModel):
    """Beekeeperへの最適化提案"""

    model_config = ConfigDict(frozen=True)

    template_name: str = Field(..., description="推薦テンプレート名")
    success_rate: float = Field(..., description="類似タスクでの成功率", ge=0.0, le=1.0)
    avg_duration_seconds: float = Field(default=0.0, description="平均所要時間（秒）", ge=0.0)
    reason: str = Field(..., description="推薦理由")
    similar_episode_count: int = Field(default=0, description="参考にした類似エピソード数", ge=0)


class ScoutReport(BaseModel):
    """Scout Beeの推薦レポート"""

    model_config = ConfigDict(frozen=True)

    verdict: ScoutVerdict = Field(..., description="判定結果")
    recommended_template: str = Field(..., description="推薦テンプレート")
    similar_count: int = Field(default=0, description="検出した類似エピソード数")
    proposal: OptimizationProposal | None = Field(default=None, description="最適化提案")
    template_stats: dict[str, TemplateStats] = Field(
        default_factory=dict, description="テンプレート別統計"
    )
