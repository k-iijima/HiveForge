"""HiveForge Core モジュール

Hiveのバックエンドロジックを提供:
- AR (Akashic Record): イベントソーシング永続化
- State: 状態機械とガバナンス
- Config: 設定管理
- Events: イベントモデル
"""

from .config import get_settings, reload_settings, HiveForgeSettings
from .events import (
    BaseEvent,
    EventType,
    generate_event_id,
    parse_event,
)
from .ar import AkashicRecord, RunProjection, build_run_projection
from .state import (
    RunStateMachine,
    TaskStateMachine,
    RequirementStateMachine,
    OscillationDetector,
)

__all__ = [
    # Config
    "get_settings",
    "reload_settings",
    "HiveForgeSettings",
    # Events
    "BaseEvent",
    "EventType",
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
