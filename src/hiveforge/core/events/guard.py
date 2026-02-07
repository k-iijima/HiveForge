"""Guard Bee イベントクラス (v1.5 M3-3)"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BaseEvent
from .types import EventType


class GuardVerificationRequestedEvent(BaseEvent):
    """Guard Bee検証要求イベント"""

    type: Literal[EventType.GUARD_VERIFICATION_REQUESTED] = EventType.GUARD_VERIFICATION_REQUESTED


class GuardPassedEvent(BaseEvent):
    """Guard Bee検証合格イベント"""

    type: Literal[EventType.GUARD_PASSED] = EventType.GUARD_PASSED


class GuardConditionalPassedEvent(BaseEvent):
    """Guard Bee条件付き合格イベント"""

    type: Literal[EventType.GUARD_CONDITIONAL_PASSED] = EventType.GUARD_CONDITIONAL_PASSED


class GuardFailedEvent(BaseEvent):
    """Guard Bee検証失敗イベント（差戻し）"""

    type: Literal[EventType.GUARD_FAILED] = EventType.GUARD_FAILED
    remand_reason: str = Field(default="", description="差戻し理由")
