"""Sentinel Hornet アラートモデル

検出された異常を表すデータクラス。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SentinelAlert:
    """Sentinel Hornetが発行するアラート"""

    alert_type: str  # loop_detected, runaway_detected, cost_exceeded, security_violation
    colony_id: str
    severity: str  # warning, critical
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
