"""Decision / Conference / Conflict イベントクラス"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


class DecisionRecordedEvent(BaseEvent):
    """Decision記録イベント"""

    type: Literal[EventType.DECISION_RECORDED] = EventType.DECISION_RECORDED


class ProposalCreatedEvent(BaseEvent):
    """提案作成イベント (v5.1)"""

    type: Literal[EventType.PROPOSAL_CREATED] = EventType.PROPOSAL_CREATED


class DecisionAppliedEvent(BaseEvent):
    """決定適用イベント (v5.1)"""

    type: Literal[EventType.DECISION_APPLIED] = EventType.DECISION_APPLIED


class DecisionSupersededEvent(BaseEvent):
    """決定上書きイベント (v5.1)"""

    type: Literal[EventType.DECISION_SUPERSEDED] = EventType.DECISION_SUPERSEDED


class ConferenceStartedEvent(BaseEvent):
    """会議開始イベント (v5.1)"""

    type: Literal[EventType.CONFERENCE_STARTED] = EventType.CONFERENCE_STARTED


class ConferenceEndedEvent(BaseEvent):
    """会議終了イベント (v5.1)"""

    type: Literal[EventType.CONFERENCE_ENDED] = EventType.CONFERENCE_ENDED


class ConflictDetectedEvent(BaseEvent):
    """衝突検出イベント (v5.1)"""

    type: Literal[EventType.CONFLICT_DETECTED] = EventType.CONFLICT_DETECTED


class ConflictResolvedEvent(BaseEvent):
    """衝突解決イベント (v5.1)"""

    type: Literal[EventType.CONFLICT_RESOLVED] = EventType.CONFLICT_RESOLVED
