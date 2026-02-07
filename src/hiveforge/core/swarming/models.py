"""Swarming Protocol データモデル

SwarmingFeatures（入力特徴量）の定義。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TemplateName(str, Enum):
    """Colonyテンプレート名"""

    SPEED = "speed"
    BALANCED = "balanced"
    QUALITY = "quality"
    RECOVERY = "recovery"


class SwarmingFeatures(BaseModel):
    """タスクの入力特徴量

    3軸で評価（各 1〜5）:
    - Complexity（複雑さ）: 技術的な困難度、コンポーネント間の結合度
    - Risk（リスク）: 失敗時の影響範囲、不可逆性
    - Urgency（緊急度）: 期限までの時間的余裕
    """

    model_config = ConfigDict(frozen=True)

    complexity: int = Field(
        default=3,
        ge=1,
        le=5,
        description="複雑さ（1=単純, 5=非常に複雑）",
    )
    risk: int = Field(
        default=3,
        ge=1,
        le=5,
        description="リスク（1=低, 5=高）",
    )
    urgency: int = Field(
        default=3,
        ge=1,
        le=5,
        description="緊急度（1=余裕あり, 5=至急）",
    )

    def to_dict(self) -> dict[str, float]:
        """Honeycomb記録用のdict変換"""
        return {
            "complexity": float(self.complexity),
            "risk": float(self.risk),
            "urgency": float(self.urgency),
        }
