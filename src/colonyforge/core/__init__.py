"""ColonyForge Core モジュール

Hiveのバックエンドロジックを提供:
- AR (Akashic Record): イベントソーシング永続化
- State: 状態機械とガバナンス
- Config: 設定管理
- Events: イベントモデル
"""

from .ar import AkashicRecord, RunProjection, build_run_projection
from .config import ColonyForgeSettings, get_settings, reload_settings
from .events import (
    BaseEvent,
    BeekeeperFeedbackEvent,
    EscalationType,
    EventType,
    QueenEscalationEvent,
    UserDirectInterventionEvent,
    generate_event_id,
    parse_event,
)
from .state import (
    OscillationDetector,
    RequirementStateMachine,
    RunStateMachine,
    TaskStateMachine,
)

__all__ = [
    # Config
    "get_settings",
    "reload_settings",
    "ColonyForgeSettings",
    # Events
    "BaseEvent",
    "EventType",
    "EscalationType",
    "UserDirectInterventionEvent",
    "QueenEscalationEvent",
    "BeekeeperFeedbackEvent",
    "generate_event_id",
    "parse_event",
    # AR
    "AkashicRecord",
    "RunProjection",
    "build_run_projection",
    # State
    "RunStateMachine",
    "TaskStateMachine",
    "RequirementStateMachine",
    "OscillationDetector",
]
