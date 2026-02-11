"""Waggle Dance 通信メッセージモデル

エージェント間通信の構造化I/Oスキーマを定義する。
Pydanticによる厳格なバリデーションで、不正なメッセージを自動検出する。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageDirection(StrEnum):
    """メッセージの方向（送信元 → 送信先）"""

    BEEKEEPER_TO_QUEEN = "beekeeper_to_queen"
    QUEEN_TO_BEEKEEPER = "queen_to_beekeeper"
    QUEEN_TO_WORKER = "queen_to_worker"
    WORKER_TO_QUEEN = "worker_to_queen"
    GUARD_RESULT = "guard_result"


class OpinionRequest(BaseModel):
    """Beekeeper → Queen Bee: 意見要求メッセージ"""

    model_config = ConfigDict(frozen=True)

    colony_id: str = Field(..., min_length=1, description="対象ColonyのID")
    question: str = Field(..., min_length=1, description="質問内容")
    context: dict[str, Any] = Field(default_factory=dict, description="追加コンテキスト")


class OpinionResponse(BaseModel):
    """Queen Bee → Beekeeper: 意見応答メッセージ"""

    model_config = ConfigDict(frozen=True)

    colony_id: str = Field(..., description="対象ColonyのID")
    answer: str = Field(..., min_length=1, description="回答内容")
    confidence: float = Field(..., ge=0.0, le=1.0, description="確信度 (0.0〜1.0)")


class TaskAssignment(BaseModel):
    """Queen Bee → Worker Bee: タスク割り当てメッセージ"""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(..., description="タスクID")
    colony_id: str = Field(..., description="ColonyのID")
    instructions: str = Field(..., min_length=1, description="作業指示")
    tools_allowed: list[str] = Field(default_factory=list, description="使用可能なツール一覧")


class TaskResult(BaseModel):
    """Worker Bee → Queen Bee: タスク結果メッセージ"""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(..., description="タスクID")
    colony_id: str = Field(..., description="ColonyのID")
    success: bool = Field(..., description="成功/失敗")
    artifacts: list[str] = Field(default_factory=list, description="成果物ファイルパス")
    evidence: dict[str, Any] = Field(default_factory=dict, description="証拠データ")
    error_message: str | None = Field(default=None, description="エラーメッセージ（失敗時）")


class ValidationError(BaseModel):
    """Waggle Dance バリデーションエラー

    Pydantic標準のValidationErrorと区別するため、
    インポート時に WDValidationError としてエイリアスする。
    """

    model_config = ConfigDict(frozen=True)

    field: str = Field(..., description="エラーが発生したフィールド名")
    message: str = Field(..., description="エラーメッセージ")

    def __contains__(self, item: str) -> bool:
        """フィールド名の存在チェック（`'field' in err` 形式をサポート）"""
        return item in type(self).model_fields


class WaggleDanceResult(BaseModel):
    """Waggle Dance バリデーション結果"""

    model_config = ConfigDict(frozen=True)

    valid: bool = Field(..., description="バリデーション合格/不合格")
    errors: list[ValidationError] = Field(default_factory=list, description="エラー一覧")
    direction: MessageDirection = Field(..., description="メッセージの方向")
