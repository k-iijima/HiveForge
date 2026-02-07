"""HiveForge イベントモデル

イミュータブルなイベントの定義とシリアライズ。
全てのイベントはAkashic Recordに永続化される。

後方互換性: 全シンボルをこの __init__.py からre-exportする。
既存の `from hiveforge.core.events import X` はそのまま動作する。
"""

# --- 列挙型 ---
from .types import (
    ConflictCategory,
    ConflictSeverity,
    DecisionScope,
    EscalationType,
    EventType,
    FailureReason,
    RiskLevel,
)

# --- 基底クラス・ユーティリティ ---
from .base import (
    BaseEvent,
    UnknownEvent,
    _serialize_value,
    compute_hash,
    generate_event_id,
)

# --- Hive / Colony ---
from .hive import (
    ColonyCompletedEvent,
    ColonyCreatedEvent,
    ColonyFailedEvent,
    ColonyStartedEvent,
    HiveClosedEvent,
    HiveCreatedEvent,
)

# --- Run / Task / Requirement ---
from .run import (
    RequirementApprovedEvent,
    RequirementCreatedEvent,
    RequirementRejectedEvent,
    RunAbortedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    TaskAssignedEvent,
    TaskBlockedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
    TaskProgressedEvent,
    TaskUnblockedEvent,
)

# --- Decision / Conference / Conflict ---
from .decision import (
    ConferenceEndedEvent,
    ConferenceStartedEvent,
    ConflictDetectedEvent,
    ConflictResolvedEvent,
    DecisionAppliedEvent,
    DecisionRecordedEvent,
    DecisionSupersededEvent,
    ProposalCreatedEvent,
)

# --- Operation / Intervention / System ---
from .operation import (
    BeekeeperFeedbackEvent,
    EmergencyStopEvent,
    ErrorEvent,
    HeartbeatEvent,
    OperationFailedEvent,
    OperationTimeoutEvent,
    QueenEscalationEvent,
    SilenceDetectedEvent,
    UserDirectInterventionEvent,
)

# --- Worker Bee ---
from .worker import (
    WorkerAssignedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerProgressEvent,
    WorkerStartedEvent,
)

# --- Guard Bee ---
from .guard import (
    GuardConditionalPassedEvent,
    GuardFailedEvent,
    GuardPassedEvent,
    GuardVerificationRequestedEvent,
)

# --- レジストリ ---
from .registry import (
    EVENT_TYPE_MAP,
    parse_event,
)

__all__ = [
    # 列挙型
    "ConflictCategory",
    "ConflictSeverity",
    "DecisionScope",
    "EscalationType",
    "EventType",
    "FailureReason",
    "RiskLevel",
    # 基底
    "BaseEvent",
    "UnknownEvent",
    "compute_hash",
    "generate_event_id",
    # Hive/Colony
    "ColonyCompletedEvent",
    "ColonyCreatedEvent",
    "ColonyFailedEvent",
    "ColonyStartedEvent",
    "HiveClosedEvent",
    "HiveCreatedEvent",
    # Run/Task/Requirement
    "RequirementApprovedEvent",
    "RequirementCreatedEvent",
    "RequirementRejectedEvent",
    "RunAbortedEvent",
    "RunCompletedEvent",
    "RunFailedEvent",
    "RunStartedEvent",
    "TaskAssignedEvent",
    "TaskBlockedEvent",
    "TaskCompletedEvent",
    "TaskCreatedEvent",
    "TaskFailedEvent",
    "TaskProgressedEvent",
    "TaskUnblockedEvent",
    # Decision/Conference/Conflict
    "ConferenceEndedEvent",
    "ConferenceStartedEvent",
    "ConflictDetectedEvent",
    "ConflictResolvedEvent",
    "DecisionAppliedEvent",
    "DecisionRecordedEvent",
    "DecisionSupersededEvent",
    "ProposalCreatedEvent",
    # Operation/Intervention/System
    "BeekeeperFeedbackEvent",
    "EmergencyStopEvent",
    "ErrorEvent",
    "HeartbeatEvent",
    "OperationFailedEvent",
    "OperationTimeoutEvent",
    "QueenEscalationEvent",
    "SilenceDetectedEvent",
    "UserDirectInterventionEvent",
    # Worker Bee
    "WorkerAssignedEvent",
    "WorkerCompletedEvent",
    "WorkerFailedEvent",
    "WorkerProgressEvent",
    "WorkerStartedEvent",
    # Guard Bee
    "GuardConditionalPassedEvent",
    "GuardFailedEvent",
    "GuardPassedEvent",
    "GuardVerificationRequestedEvent",
    # レジストリ
    "EVENT_TYPE_MAP",
    "parse_event",
]
