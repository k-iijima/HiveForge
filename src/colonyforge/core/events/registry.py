"""イベントレジストリとパーサー

EVENT_TYPE_MAP と parse_event() の定義。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .base import BaseEvent, UnknownEvent, generate_event_id
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
from .github import (
    GitHubCommentAddedEvent,
    GitHubIssueClosedEvent,
    GitHubIssueCreatedEvent,
    GitHubIssueUpdatedEvent,
    GitHubLabelAppliedEvent,
    GitHubProjectSyncedEvent,
)
from .guard import (
    GuardConditionalPassedEvent,
    GuardFailedEvent,
    GuardPassedEvent,
    GuardVerificationRequestedEvent,
)
from .hive import (
    ColonyCompletedEvent,
    ColonyCreatedEvent,
    ColonyFailedEvent,
    ColonyStartedEvent,
    ColonySuspendedEvent,
    HiveClosedEvent,
    HiveCreatedEvent,
)
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
from .pipeline import (
    PipelineCompletedEvent,
    PipelineStartedEvent,
    PlanApprovalRequiredEvent,
    PlanFallbackActivatedEvent,
    PlanValidationFailedEvent,
)
from .ra import (
    RAChallengeReviewedEvent,
    RAClarifyGeneratedEvent,
    RACompletedEvent,
    RAContextEnrichedEvent,
    RAGateDecidedEvent,
    RAHypothesisBuiltEvent,
    RAIntakeReceivedEvent,
    RARefereeComparedEvent,
    RAReqChangedEvent,
    RASpecSynthesizedEvent,
    RATriageCompletedEvent,
    RAUserRespondedEvent,
    RAWebResearchedEvent,
    RAWebSkippedEvent,
)
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
from .sentinel import (
    SentinelAlertRaisedEvent,
    SentinelKpiDegradationEvent,
    SentinelQuarantineEvent,
    SentinelReportEvent,
    SentinelRollbackEvent,
)
from .types import EventType
from .waggle import (
    WaggleDanceValidatedEvent,
    WaggleDanceViolationEvent,
)
from .worker import (
    WorkerAssignedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerProgressEvent,
    WorkerStartedEvent,
)

# イベントタイプからクラスへのマッピング
EVENT_TYPE_MAP: dict[EventType, type[BaseEvent]] = {
    # Hive
    EventType.HIVE_CREATED: HiveCreatedEvent,
    EventType.HIVE_CLOSED: HiveClosedEvent,
    # Colony
    EventType.COLONY_CREATED: ColonyCreatedEvent,
    EventType.COLONY_STARTED: ColonyStartedEvent,
    EventType.COLONY_SUSPENDED: ColonySuspendedEvent,
    EventType.COLONY_COMPLETED: ColonyCompletedEvent,
    EventType.COLONY_FAILED: ColonyFailedEvent,
    # Run
    EventType.RUN_STARTED: RunStartedEvent,
    EventType.RUN_COMPLETED: RunCompletedEvent,
    EventType.RUN_FAILED: RunFailedEvent,
    EventType.RUN_ABORTED: RunAbortedEvent,
    EventType.TASK_CREATED: TaskCreatedEvent,
    EventType.TASK_ASSIGNED: TaskAssignedEvent,
    EventType.TASK_PROGRESSED: TaskProgressedEvent,
    EventType.TASK_COMPLETED: TaskCompletedEvent,
    EventType.TASK_FAILED: TaskFailedEvent,
    EventType.TASK_BLOCKED: TaskBlockedEvent,
    EventType.TASK_UNBLOCKED: TaskUnblockedEvent,
    EventType.REQUIREMENT_CREATED: RequirementCreatedEvent,
    EventType.REQUIREMENT_APPROVED: RequirementApprovedEvent,
    EventType.REQUIREMENT_REJECTED: RequirementRejectedEvent,
    EventType.DECISION_RECORDED: DecisionRecordedEvent,
    # Decision Protocol (v5.1)
    EventType.PROPOSAL_CREATED: ProposalCreatedEvent,
    EventType.DECISION_APPLIED: DecisionAppliedEvent,
    EventType.DECISION_SUPERSEDED: DecisionSupersededEvent,
    # Conference (v5.1)
    EventType.CONFERENCE_STARTED: ConferenceStartedEvent,
    EventType.CONFERENCE_ENDED: ConferenceEndedEvent,
    # Conflict Detection (v5.1)
    EventType.CONFLICT_DETECTED: ConflictDetectedEvent,
    EventType.CONFLICT_RESOLVED: ConflictResolvedEvent,
    # Operation Failure/Timeout (v5.1)
    EventType.OPERATION_TIMEOUT: OperationTimeoutEvent,
    EventType.OPERATION_FAILED: OperationFailedEvent,
    # Direct Intervention (v5.2)
    EventType.USER_DIRECT_INTERVENTION: UserDirectInterventionEvent,
    EventType.QUEEN_ESCALATION: QueenEscalationEvent,
    EventType.BEEKEEPER_FEEDBACK: BeekeeperFeedbackEvent,
    EventType.HEARTBEAT: HeartbeatEvent,
    EventType.ERROR: ErrorEvent,
    EventType.SILENCE_DETECTED: SilenceDetectedEvent,
    EventType.EMERGENCY_STOP: EmergencyStopEvent,
    # Worker Bee (Phase 2)
    EventType.WORKER_ASSIGNED: WorkerAssignedEvent,
    EventType.WORKER_STARTED: WorkerStartedEvent,
    EventType.WORKER_PROGRESS: WorkerProgressEvent,
    EventType.WORKER_COMPLETED: WorkerCompletedEvent,
    EventType.WORKER_FAILED: WorkerFailedEvent,
    # Guard Bee (v1.5 M3-3)
    EventType.GUARD_VERIFICATION_REQUESTED: GuardVerificationRequestedEvent,
    EventType.GUARD_PASSED: GuardPassedEvent,
    EventType.GUARD_CONDITIONAL_PASSED: GuardConditionalPassedEvent,
    EventType.GUARD_FAILED: GuardFailedEvent,
    # Sentinel Hornet (M2-0 / M3-6)
    EventType.SENTINEL_ALERT_RAISED: SentinelAlertRaisedEvent,
    EventType.SENTINEL_REPORT: SentinelReportEvent,
    EventType.SENTINEL_ROLLBACK: SentinelRollbackEvent,
    EventType.SENTINEL_QUARANTINE: SentinelQuarantineEvent,
    EventType.SENTINEL_KPI_DEGRADATION: SentinelKpiDegradationEvent,
    # Waggle Dance (M3-7)
    EventType.WAGGLE_DANCE_VALIDATED: WaggleDanceValidatedEvent,
    EventType.WAGGLE_DANCE_VIOLATION: WaggleDanceViolationEvent,
    # Pipeline (監査性強化)
    EventType.PIPELINE_STARTED: PipelineStartedEvent,
    EventType.PIPELINE_COMPLETED: PipelineCompletedEvent,
    EventType.PLAN_VALIDATION_FAILED: PlanValidationFailedEvent,
    EventType.PLAN_APPROVAL_REQUIRED: PlanApprovalRequiredEvent,
    EventType.PLAN_FALLBACK_ACTIVATED: PlanFallbackActivatedEvent,
    # LLM
    EventType.LLM_REQUEST: LLMRequestEvent,
    EventType.LLM_RESPONSE: LLMResponseEvent,
    # GitHub Projection
    EventType.GITHUB_ISSUE_CREATED: GitHubIssueCreatedEvent,
    EventType.GITHUB_ISSUE_UPDATED: GitHubIssueUpdatedEvent,
    EventType.GITHUB_ISSUE_CLOSED: GitHubIssueClosedEvent,
    EventType.GITHUB_COMMENT_ADDED: GitHubCommentAddedEvent,
    EventType.GITHUB_LABEL_APPLIED: GitHubLabelAppliedEvent,
    EventType.GITHUB_PROJECT_SYNCED: GitHubProjectSyncedEvent,
    # Requirement Analysis Colony (Phase 1, §6.1)
    EventType.RA_INTAKE_RECEIVED: RAIntakeReceivedEvent,
    EventType.RA_TRIAGE_COMPLETED: RATriageCompletedEvent,
    EventType.RA_CONTEXT_ENRICHED: RAContextEnrichedEvent,
    EventType.RA_HYPOTHESIS_BUILT: RAHypothesisBuiltEvent,
    EventType.RA_CLARIFY_GENERATED: RAClarifyGeneratedEvent,
    EventType.RA_USER_RESPONDED: RAUserRespondedEvent,
    EventType.RA_SPEC_SYNTHESIZED: RASpecSynthesizedEvent,
    EventType.RA_CHALLENGE_REVIEWED: RAChallengeReviewedEvent,
    EventType.RA_GATE_DECIDED: RAGateDecidedEvent,
    EventType.RA_COMPLETED: RACompletedEvent,
    EventType.RA_REQ_CHANGED: RAReqChangedEvent,
    # Phase 2 追加
    EventType.RA_WEB_RESEARCHED: RAWebResearchedEvent,
    EventType.RA_WEB_SKIPPED: RAWebSkippedEvent,
    EventType.RA_REFEREE_COMPARED: RARefereeComparedEvent,
}


def parse_event(data: dict[str, Any] | str) -> BaseEvent:
    """イベントデータをパースして適切なイベントクラスに変換

    未知のイベントタイプはUnknownEventとして返す（前方互換性）。
    """
    if isinstance(data, str):
        data = json.loads(data)

    # json.loadsの結果はdict[str, Any]であることを保証（型ナローイング）
    assert isinstance(data, dict)

    original_data = dict(data)

    try:
        event_type = EventType(data["type"])
        event_class = EVENT_TYPE_MAP.get(event_type, BaseEvent)
        # strict=Trueモードではstr→StrEnum/datetime自動変換されないため、
        # 事前に型変換を行う
        data = dict(data)
        data["type"] = event_type
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return event_class.model_validate(data)
    except ValueError:
        return UnknownEvent(
            type=data.get("type", "unknown"),
            id=data.get("id", generate_event_id()),
            actor=data.get("actor", "unknown"),
            payload=data.get("payload", {}),
            run_id=data.get("run_id"),
            task_id=data.get("task_id"),
            prev_hash=data.get("prev_hash"),
            parents=data.get("parents", []),
            original_data=original_data,
        )
