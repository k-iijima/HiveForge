"""Intervention データモデル

介入・エスカレーション・フィードバックのPydanticモデル。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class InterventionType(StrEnum):
    """介入の種別"""

    USER_INTERVENTION = "user_intervention"
    QUEEN_ESCALATION = "queen_escalation"
    BEEKEEPER_FEEDBACK = "beekeeper_feedback"


class EscalationStatus(StrEnum):
    """エスカレーションの状態"""

    PENDING = "pending"
    RESOLVED = "resolved"


class InterventionRecord(BaseModel):
    """ユーザー直接介入の記録"""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="イベントID")
    type: InterventionType = Field(
        default=InterventionType.USER_INTERVENTION, description="介入種別"
    )
    colony_id: str = Field(..., description="対象Colony ID")
    instruction: str = Field(..., description="直接指示内容")
    reason: str = Field(default="", description="介入理由")
    share_with_beekeeper: bool = Field(default=True, description="Beekeeperに共有するか")
    timestamp: str = Field(..., description="タイムスタンプ (ISO形式)")


class EscalationRecord(BaseModel):
    """Queen直訴の記録"""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="イベントID")
    type: InterventionType = Field(
        default=InterventionType.QUEEN_ESCALATION, description="介入種別"
    )
    colony_id: str = Field(..., description="Colony ID")
    escalation_type: str = Field(..., description="エスカレーション種別")
    summary: str = Field(..., description="問題要約")
    details: str = Field(default="", description="詳細説明")
    suggested_actions: list[str] = Field(default_factory=list, description="提案アクション")
    beekeeper_context: str = Field(default="", description="Beekeeperとの経緯")
    status: EscalationStatus = Field(default=EscalationStatus.PENDING, description="状態")
    timestamp: str = Field(..., description="タイムスタンプ (ISO形式)")


class FeedbackRecord(BaseModel):
    """Beekeeperフィードバックの記録"""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="イベントID")
    type: InterventionType = Field(
        default=InterventionType.BEEKEEPER_FEEDBACK, description="介入種別"
    )
    escalation_id: str = Field(..., description="対応したエスカレーション/介入のID")
    resolution: str = Field(..., description="解決方法")
    beekeeper_adjustment: dict = Field(default_factory=dict, description="Beekeeperへの調整")
    lesson_learned: str = Field(default="", description="学んだ教訓")
    timestamp: str = Field(..., description="タイムスタンプ (ISO形式)")
