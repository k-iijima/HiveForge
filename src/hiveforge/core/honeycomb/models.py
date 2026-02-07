"""Honeycomb データモデル

Episode, FailureClass, KPIScores の定義。
Pydanticで厳格な型検証を行う。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Outcome(str, Enum):
    """エピソードの結果"""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class FailureClass(str, Enum):
    """失敗分類

    | 分類 | 説明 |
    |------|------|
    | SPECIFICATION_ERROR | 仕様の不明確さ・矛盾 |
    | DESIGN_ERROR | 設計判断の誤り |
    | IMPLEMENTATION_ERROR | コーディングミス |
    | INTEGRATION_ERROR | Colony間の結合不整合 |
    | ENVIRONMENT_ERROR | 環境固有の問題 |
    | TIMEOUT | 時間切れ |
    """

    SPECIFICATION_ERROR = "specification_error"
    DESIGN_ERROR = "design_error"
    IMPLEMENTATION_ERROR = "implementation_error"
    INTEGRATION_ERROR = "integration_error"
    ENVIRONMENT_ERROR = "environment_error"
    TIMEOUT = "timeout"


class KPIScores(BaseModel):
    """KPI計測値

    5つのKPI指標のスコアを保持する。
    各スコアは0.0〜1.0または計測値（秒数、トークン数）。
    """

    model_config = ConfigDict(frozen=True)

    correctness: float | None = Field(
        default=None,
        description="正確性: Guard Beeの一次合格率",
        ge=0.0,
        le=1.0,
    )
    repeatability: float | None = Field(
        default=None,
        description="再現性: 同一タスク種別の成功率分散",
        ge=0.0,
    )
    lead_time_seconds: float | None = Field(
        default=None,
        description="リードタイム: タスク開始→完了の秒数",
        ge=0.0,
    )
    incident_rate: float | None = Field(
        default=None,
        description="インシデント率: Sentinel Hornetの介入頻度",
        ge=0.0,
        le=1.0,
    )
    recurrence_rate: float | None = Field(
        default=None,
        description="再発率: 同一分類の失敗が再発する率",
        ge=0.0,
        le=1.0,
    )


class Episode(BaseModel):
    """実行エピソード

    Run/Taskの完了時に記録される実行履歴。
    学習・KPI計測の基本単位。
    """

    model_config = ConfigDict(frozen=True)

    episode_id: str = Field(..., description="エピソードID (ULID)", examples=["01JKXYZ..."])
    run_id: str = Field(..., description="対応するRun ID")
    colony_id: str = Field(..., description="対応するColony ID")
    template_used: str = Field(default="balanced", description="使用したColonyテンプレート")

    # 入力: タスク特徴量（Swarming Protocolスコア）
    # SwarmingFeaturesがまだ未実装のためdictで保持
    task_features: dict[str, float] = Field(
        default_factory=dict,
        description="タスク特徴量（SwarmingFeatures）",
    )

    # 結果
    outcome: Outcome = Field(..., description="結果")
    duration_seconds: float = Field(default=0.0, description="所要時間（秒）", ge=0.0)
    token_count: int = Field(default=0, description="使用トークン数", ge=0)

    # 失敗分類（失敗時のみ）
    failure_class: FailureClass | None = Field(default=None, description="失敗分類")

    # KPI計測値
    kpi_scores: KPIScores = Field(
        default_factory=KPIScores,
        description="KPI計測値",
    )

    # 因果リンク
    parent_episode_ids: list[str] = Field(
        default_factory=list,
        description="前回の試行エピソードID",
    )

    # メタデータ
    goal: str = Field(default="", description="タスクの目標")
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, description="追加メタデータ"
    )
