"""Run / Task / Requirement イベントクラス"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


# Run イベント
class RunStartedEvent(BaseEvent):
    """Run開始イベント"""

    type: Literal[EventType.RUN_STARTED] = EventType.RUN_STARTED


class RunCompletedEvent(BaseEvent):
    """Run完了イベント"""

    type: Literal[EventType.RUN_COMPLETED] = EventType.RUN_COMPLETED


class RunFailedEvent(BaseEvent):
    """Run失敗イベント"""

    type: Literal[EventType.RUN_FAILED] = EventType.RUN_FAILED


class RunAbortedEvent(BaseEvent):
    """Run中断イベント"""

    type: Literal[EventType.RUN_ABORTED] = EventType.RUN_ABORTED


# Task イベント
class TaskCreatedEvent(BaseEvent):
    """Task作成イベント"""

    type: Literal[EventType.TASK_CREATED] = EventType.TASK_CREATED


class TaskAssignedEvent(BaseEvent):
    """Task割り当てイベント"""

    type: Literal[EventType.TASK_ASSIGNED] = EventType.TASK_ASSIGNED


class TaskProgressedEvent(BaseEvent):
    """Task進捗イベント"""

    type: Literal[EventType.TASK_PROGRESSED] = EventType.TASK_PROGRESSED


class TaskCompletedEvent(BaseEvent):
    """Task完了イベント"""

    type: Literal[EventType.TASK_COMPLETED] = EventType.TASK_COMPLETED


class TaskFailedEvent(BaseEvent):
    """Task失敗イベント"""

    type: Literal[EventType.TASK_FAILED] = EventType.TASK_FAILED


class TaskBlockedEvent(BaseEvent):
    """Taskブロックイベント"""

    type: Literal[EventType.TASK_BLOCKED] = EventType.TASK_BLOCKED


class TaskUnblockedEvent(BaseEvent):
    """Taskブロック解除イベント"""

    type: Literal[EventType.TASK_UNBLOCKED] = EventType.TASK_UNBLOCKED


# Requirement イベント
class RequirementCreatedEvent(BaseEvent):
    """Requirement作成イベント"""

    type: Literal[EventType.REQUIREMENT_CREATED] = EventType.REQUIREMENT_CREATED


class RequirementApprovedEvent(BaseEvent):
    """Requirement承認イベント"""

    type: Literal[EventType.REQUIREMENT_APPROVED] = EventType.REQUIREMENT_APPROVED


class RequirementRejectedEvent(BaseEvent):
    """Requirement拒否イベント"""

    type: Literal[EventType.REQUIREMENT_REJECTED] = EventType.REQUIREMENT_REJECTED
