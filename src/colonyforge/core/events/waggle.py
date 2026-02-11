"""Waggle Dance イベントクラス (M3-7)

エージェント間メッセージのスキーマ検証結果を記録するイベント。
"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


class WaggleDanceValidatedEvent(BaseEvent):
    """Waggle Dance 検証成功イベント"""

    type: Literal[EventType.WAGGLE_DANCE_VALIDATED] = EventType.WAGGLE_DANCE_VALIDATED


class WaggleDanceViolationEvent(BaseEvent):
    """Waggle Dance 検証違反イベント"""

    type: Literal[EventType.WAGGLE_DANCE_VIOLATION] = EventType.WAGGLE_DANCE_VIOLATION
