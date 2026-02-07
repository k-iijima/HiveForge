"""Hive / Colony イベントクラス"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


# Hive イベント
class HiveCreatedEvent(BaseEvent):
    """Hive作成イベント

    Hiveは複数のColonyを管理する最上位のコンテナ。
    """

    type: Literal[EventType.HIVE_CREATED] = EventType.HIVE_CREATED


class HiveClosedEvent(BaseEvent):
    """Hive終了イベント"""

    type: Literal[EventType.HIVE_CLOSED] = EventType.HIVE_CLOSED


# Colony イベント
class ColonyCreatedEvent(BaseEvent):
    """Colony作成イベント"""

    type: Literal[EventType.COLONY_CREATED] = EventType.COLONY_CREATED


class ColonyStartedEvent(BaseEvent):
    """Colony開始イベント"""

    type: Literal[EventType.COLONY_STARTED] = EventType.COLONY_STARTED


class ColonyCompletedEvent(BaseEvent):
    """Colony完了イベント"""

    type: Literal[EventType.COLONY_COMPLETED] = EventType.COLONY_COMPLETED


class ColonyFailedEvent(BaseEvent):
    """Colony失敗イベント"""

    type: Literal[EventType.COLONY_FAILED] = EventType.COLONY_FAILED
