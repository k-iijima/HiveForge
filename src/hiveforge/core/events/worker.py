"""Worker Bee イベントクラス (Phase 2)"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BaseEvent
from .types import EventType


class WorkerAssignedEvent(BaseEvent):
    """Worker Beeにタスク割り当てイベント"""

    type: Literal[EventType.WORKER_ASSIGNED] = EventType.WORKER_ASSIGNED
    worker_id: str = Field(..., description="割り当て先Worker BeeのID")


class WorkerStartedEvent(BaseEvent):
    """Worker Bee作業開始イベント"""

    type: Literal[EventType.WORKER_STARTED] = EventType.WORKER_STARTED
    worker_id: str = Field(..., description="Worker BeeのID")


class WorkerProgressEvent(BaseEvent):
    """Worker Bee進捗報告イベント"""

    type: Literal[EventType.WORKER_PROGRESS] = EventType.WORKER_PROGRESS
    worker_id: str = Field(..., description="Worker BeeのID")
    progress: int = Field(..., ge=0, le=100, description="進捗率 (0-100)")


class WorkerCompletedEvent(BaseEvent):
    """Worker Bee作業完了イベント"""

    type: Literal[EventType.WORKER_COMPLETED] = EventType.WORKER_COMPLETED
    worker_id: str = Field(..., description="Worker BeeのID")


class WorkerFailedEvent(BaseEvent):
    """Worker Bee作業失敗イベント"""

    type: Literal[EventType.WORKER_FAILED] = EventType.WORKER_FAILED
    worker_id: str = Field(..., description="Worker BeeのID")
    reason: str = Field(default="", description="失敗理由")
