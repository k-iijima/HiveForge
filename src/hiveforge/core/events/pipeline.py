"""Pipeline イベントクラス

Queen Bee 実行パイプラインの各段階を記録するイベント。
"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


class PipelineStartedEvent(BaseEvent):
    """パイプライン開始イベント"""

    type: Literal[EventType.PIPELINE_STARTED] = EventType.PIPELINE_STARTED


class PipelineCompletedEvent(BaseEvent):
    """パイプライン完了イベント"""

    type: Literal[EventType.PIPELINE_COMPLETED] = EventType.PIPELINE_COMPLETED


class PlanValidationFailedEvent(BaseEvent):
    """プラン検証失敗イベント"""

    type: Literal[EventType.PLAN_VALIDATION_FAILED] = EventType.PLAN_VALIDATION_FAILED


class PlanApprovalRequiredEvent(BaseEvent):
    """プラン承認要求イベント"""

    type: Literal[EventType.PLAN_APPROVAL_REQUIRED] = EventType.PLAN_APPROVAL_REQUIRED


class PlanFallbackActivatedEvent(BaseEvent):
    """プランフォールバック発動イベント"""

    type: Literal[EventType.PLAN_FALLBACK_ACTIVATED] = EventType.PLAN_FALLBACK_ACTIVATED
