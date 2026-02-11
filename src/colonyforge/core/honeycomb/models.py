"""Honeycomb データモデル

Episode, FailureClass, KPIScores の定義。
Pydanticで厳格な型検証を行う。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Outcome(StrEnum):
    """エピソードの結果"""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class FailureClass(StrEnum):
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

    5つの基本KPI指標のスコアを保持する。
    各スコアは0.0〜1.0または計測値（秒数、トークン数）。
    """

    model_config = ConfigDict(strict=True, frozen=True)

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


class CollaborationMetrics(BaseModel):
    """協調品質メトリクス

    エージェント間の協調効率を計測する。
    Honeycomb Episode + ARイベントから算出。

    参考: Mixture-of-Agents (Wang et al., 2024), AgentVerse (Chen et al., 2023)
    """

    model_config = ConfigDict(strict=True, frozen=True)

    rework_rate: float | None = Field(
        default=None,
        description="再作業率: Guard Bee差戻し後の再作業割合",
        ge=0.0,
        le=1.0,
    )
    escalation_ratio: float | None = Field(
        default=None,
        description="エスカレーション率: Queen Bee→Beekeeper委譲の割合",
        ge=0.0,
        le=1.0,
    )
    n_proposal_yield: float | None = Field(
        default=None,
        description="N案歩留まり: Referee Bee選抜 / 生成候補",
        ge=0.0,
        le=1.0,
    )
    cost_per_task_tokens: float | None = Field(
        default=None,
        description="タスク当り平均トークン消費",
        ge=0.0,
    )
    collaboration_overhead: float | None = Field(
        default=None,
        description="協調オーバーヘッド: Sentinel介入を含む全失敗/リワーク比率",
        ge=0.0,
    )


class GateAccuracyMetrics(BaseModel):
    """ゲート精度メトリクス

    Guard Bee / Forager Bee / Sentinel Hornet の判定精度。
    False Accept Rate (FAR) / False Reject Rate (FRR) で評価。

    参考: AgentBench (Liu et al., ICLR 2024) の失敗分類
    """

    model_config = ConfigDict(strict=True, frozen=True)

    guard_pass_rate: float | None = Field(
        default=None,
        description="Guard Bee合格率: PASS / 全検証",
        ge=0.0,
        le=1.0,
    )
    guard_conditional_pass_rate: float | None = Field(
        default=None,
        description="Guard Bee条件付合格率: CONDITIONAL_PASS / 全検証",
        ge=0.0,
        le=1.0,
    )
    guard_fail_rate: float | None = Field(
        default=None,
        description="Guard Bee不合格率: FAIL / 全検証",
        ge=0.0,
        le=1.0,
    )
    sentinel_detection_rate: float | None = Field(
        default=None,
        description="Sentinel検知率: alert発出 / 全イベント期間",
        ge=0.0,
    )
    sentinel_false_alarm_rate: float | None = Field(
        default=None,
        description="Sentinel偽アラーム率: 誤検知 / 全alert",
        ge=0.0,
        le=1.0,
    )


class EvaluationSummary(BaseModel):
    """包括的評価サマリー

    基本KPI + 協調メトリクス + ゲート精度を統合。
    KPIダッシュボードの表示データモデル。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    total_episodes: int = Field(default=0, description="総エピソード数", ge=0)
    colony_count: int = Field(default=0, description="Colony数", ge=0)

    kpi: KPIScores = Field(default_factory=KPIScores, description="基本KPI")
    collaboration: CollaborationMetrics = Field(
        default_factory=CollaborationMetrics,
        description="協調品質メトリクス",
    )
    gate_accuracy: GateAccuracyMetrics = Field(
        default_factory=GateAccuracyMetrics,
        description="ゲート精度メトリクス",
    )

    outcomes: dict[str, int] = Field(default_factory=dict, description="Outcome別件数")
    failure_classes: dict[str, int] = Field(default_factory=dict, description="FailureClass別件数")


class Episode(BaseModel):
    """実行エピソード

    Run/Taskの完了時に記録される実行履歴。
    学習・KPI計測の基本単位。
    """

    model_config = ConfigDict(strict=True, frozen=True)

    episode_id: str = Field(..., description="エピソードID (ULID)", examples=["01JKXYZ..."])
    run_id: str = Field(..., description="対応するRun ID")
    colony_id: str = Field(..., description="対応するColony ID")
    template_used: str = Field(default="balanced", description="使用したColonyテンプレート")

    # 入力: タスク特徴量（Swarming Protocolスコア）
    # SwarmingFeaturesの値をdictで保持（complexity, risk, urgency）
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

    # Sentinel Hornet 介入回数（P-02）
    sentinel_intervention_count: int = Field(
        default=0,
        ge=0,
        description="Sentinel Hornet介入回数（alert, rollback, quarantine, kpi_degradation, emergency_stop）",
    )

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
