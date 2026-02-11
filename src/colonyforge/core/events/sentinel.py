"""Sentinel Hornet イベントクラス

監視・異常検出・ロールバック・隔離・KPI劣化のイベント。
"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


class SentinelAlertRaisedEvent(BaseEvent):
    """Sentinel Hornet アラート発行イベント"""

    type: Literal[EventType.SENTINEL_ALERT_RAISED] = EventType.SENTINEL_ALERT_RAISED


class SentinelReportEvent(BaseEvent):
    """Sentinel Hornet 監視レポートイベント"""

    type: Literal[EventType.SENTINEL_REPORT] = EventType.SENTINEL_REPORT


class SentinelRollbackEvent(BaseEvent):
    """Sentinel Hornet ロールバックイベント (M3-6)"""

    type: Literal[EventType.SENTINEL_ROLLBACK] = EventType.SENTINEL_ROLLBACK


class SentinelQuarantineEvent(BaseEvent):
    """Sentinel Hornet 隔離イベント (M3-6)"""

    type: Literal[EventType.SENTINEL_QUARANTINE] = EventType.SENTINEL_QUARANTINE


class SentinelKpiDegradationEvent(BaseEvent):
    """Sentinel Hornet KPI劣化イベント (M3-6)"""

    type: Literal[EventType.SENTINEL_KPI_DEGRADATION] = EventType.SENTINEL_KPI_DEGRADATION
