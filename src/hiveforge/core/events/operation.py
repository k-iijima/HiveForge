"""Operation / Intervention / System イベントクラス"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


# Operation Failure/Timeout (v5.1)
class OperationTimeoutEvent(BaseEvent):
    """タイムアウトイベント"""

    type: Literal[EventType.OPERATION_TIMEOUT] = EventType.OPERATION_TIMEOUT


class OperationFailedEvent(BaseEvent):
    """操作失敗イベント"""

    type: Literal[EventType.OPERATION_FAILED] = EventType.OPERATION_FAILED


# Direct Intervention (v5.2)
class UserDirectInterventionEvent(BaseEvent):
    """ユーザー直接介入イベント"""

    type: Literal[EventType.USER_DIRECT_INTERVENTION] = EventType.USER_DIRECT_INTERVENTION


class QueenEscalationEvent(BaseEvent):
    """Queen Bee直訴イベント"""

    type: Literal[EventType.QUEEN_ESCALATION] = EventType.QUEEN_ESCALATION


class BeekeeperFeedbackEvent(BaseEvent):
    """Beekeeper改善フィードバックイベント"""

    type: Literal[EventType.BEEKEEPER_FEEDBACK] = EventType.BEEKEEPER_FEEDBACK


# System イベント
class HeartbeatEvent(BaseEvent):
    """ハートビートイベント"""

    type: Literal[EventType.HEARTBEAT] = EventType.HEARTBEAT


class ErrorEvent(BaseEvent):
    """エラーイベント"""

    type: Literal[EventType.ERROR] = EventType.ERROR


class SilenceDetectedEvent(BaseEvent):
    """沈黙検出イベント"""

    type: Literal[EventType.SILENCE_DETECTED] = EventType.SILENCE_DETECTED


class EmergencyStopEvent(BaseEvent):
    """緊急停止イベント"""

    type: Literal[EventType.EMERGENCY_STOP] = EventType.EMERGENCY_STOP


# LLM イベント
class LLMRequestEvent(BaseEvent):
    """LLMリクエスト送信イベント"""

    type: Literal[EventType.LLM_REQUEST] = EventType.LLM_REQUEST


class LLMResponseEvent(BaseEvent):
    """LLMレスポンス受信イベント"""

    type: Literal[EventType.LLM_RESPONSE] = EventType.LLM_RESPONSE
