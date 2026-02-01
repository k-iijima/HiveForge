"""Beekeeper エージェント

ユーザーとHive/Colonyの橋渡し役。
ユーザーの指示をQueen Beeに伝達し、結果を集約して報告する。
"""

from .server import BeekeeperMCPServer
from .session import BeekeeperSession, BeekeeperSessionManager, SessionState
from .projection import BeekeeperProjection, build_beekeeper_projection
from .escalation import (
    Escalation,
    EscalationType,
    EscalationSeverity,
    EscalationStatus,
    EscalationManager,
)

__all__ = [
    # Server
    "BeekeeperMCPServer",
    # Session
    "BeekeeperSession",
    "BeekeeperSessionManager",
    "SessionState",
    # Projection
    "BeekeeperProjection",
    "build_beekeeper_projection",
    # Escalation
    "Escalation",
    "EscalationType",
    "EscalationSeverity",
    "EscalationStatus",
    "EscalationManager",
]
