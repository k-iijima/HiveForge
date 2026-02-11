"""ColonyForge イベントモデル

イミュータブルなイベントの定義とシリアライズ。
全てのイベントはAkashic Recordに永続化される。

後方互換性: 全シンボルをこの __init__.py からre-exportする。
既存の `from colonyforge.core.events import X` はそのまま動作する。
"""

# --- 列挙型 ---
# --- 基底クラス・ユーティリティ ---
from .base import (
    MAX_ORIGINAL_DATA_SIZE,
    BaseEvent,
    UnknownEvent,
    _serialize_value,
    compute_hash,
    generate_event_id,
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

# --- GitHub Projection ---
from .github import (
    GitHubCommentAddedEvent,
    GitHubIssueClosedEvent,
    GitHubIssueCreatedEvent,
    GitHubIssueUpdatedEvent,
    GitHubLabelAppliedEvent,
    GitHubProjectSyncedEvent,
)

# --- Guard Bee ---
from .guard import (
    GuardConditionalPassedEvent,
    GuardFailedEvent,
    GuardPassedEvent,
    GuardVerificationRequestedEvent,
)

# --- Hive / Colony ---
from .hive import (
    ColonyCompletedEvent,
    ColonyCreatedEvent,
    ColonyFailedEvent,
    ColonyStartedEvent,
    ColonySuspendedEvent,
    HiveClosedEvent,
    HiveCreatedEvent,
)

# --- Operation / Intervention / System ---
from .operation import (
    BeekeeperFeedbackEvent,
    EmergencyStopEvent,
    ErrorEvent,
    HeartbeatEvent,
    LLMRequestEvent,
    LLMResponseEvent,
    OperationFailedEvent,
    OperationTimeoutEvent,
    QueenEscalationEvent,
    SilenceDetectedEvent,
    UserDirectInterventionEvent,
)

# --- Pipeline ---
from .pipeline import (
    PipelineCompletedEvent,
    PipelineStartedEvent,
    PlanApprovalRequiredEvent,
    PlanFallbackActivatedEvent,
    PlanValidationFailedEvent,
)

# --- レジストリ ---
from .registry import (
    EVENT_TYPE_MAP,
    parse_event,
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

# --- Sentinel Hornet ---
from .sentinel import (
    SentinelAlertRaisedEvent,
    SentinelKpiDegradationEvent,
    SentinelQuarantineEvent,
    SentinelReportEvent,
    SentinelRollbackEvent,
)
from .types import (
    ConflictCategory,
    ConflictSeverity,
    DecisionScope,
    EscalationType,
    EventType,
    FailureReason,
    RiskLevel,
)

# --- Waggle Dance ---
from .waggle import (
    WaggleDanceValidatedEvent,
    WaggleDanceViolationEvent,
)

# --- Worker Bee ---
from .worker import (
    WorkerAssignedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerProgressEvent,
    WorkerStartedEvent,
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
    "MAX_ORIGINAL_DATA_SIZE",
    "UnknownEvent",
    "_serialize_value",
    "compute_hash",
    "generate_event_id",
    # Hive/Colony
    "ColonyCompletedEvent",
    "ColonyCreatedEvent",
    "ColonyFailedEvent",
    "ColonyStartedEvent",
    "ColonySuspendedEvent",
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
    "LLMRequestEvent",
    "LLMResponseEvent",
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
    # Sentinel Hornet
    "SentinelAlertRaisedEvent",
    "SentinelKpiDegradationEvent",
    "SentinelQuarantineEvent",
    "SentinelReportEvent",
    "SentinelRollbackEvent",
    # Waggle Dance
    "WaggleDanceValidatedEvent",
    "WaggleDanceViolationEvent",
    # Pipeline
    "PipelineCompletedEvent",
    "PipelineStartedEvent",
    "PlanApprovalRequiredEvent",
    "PlanFallbackActivatedEvent",
    "PlanValidationFailedEvent",
    # GitHub Projection
    "GitHubCommentAddedEvent",
    "GitHubIssueClosedEvent",
    "GitHubIssueCreatedEvent",
    "GitHubIssueUpdatedEvent",
    "GitHubLabelAppliedEvent",
    "GitHubProjectSyncedEvent",
    # レジストリ
    "EVENT_TYPE_MAP",
    "parse_event",
]
