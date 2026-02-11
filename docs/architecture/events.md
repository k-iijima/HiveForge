# Event Types

All state changes in HiveForge are recorded as typed, immutable events in the Akashic Record.

## Event Schema

Every event shares a common base structure:

```python
class BaseEvent(BaseModel):
    event_id: str       # ULID (time-ordered unique ID)
    run_id: str         # Owning Run ID
    event_type: EventType
    timestamp: str      # ISO 8601
    data: dict          # Event-specific payload
    hash: str           # SHA-256 of JCS-serialized event
    parent_hash: str    # Previous event's hash (chain integrity)
```

## Event Type Reference

### Hive Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `HIVE_CREATED` | `hive.created` | A new Hive was created |
| `HIVE_CLOSED` | `hive.closed` | A Hive was closed |

### Colony Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `COLONY_CREATED` | `colony.created` | A new Colony was created |
| `COLONY_STARTED` | `colony.started` | Colony work began |
| `COLONY_SUSPENDED` | `colony.suspended` | Colony was suspended |
| `COLONY_COMPLETED` | `colony.completed` | Colony finished successfully |
| `COLONY_FAILED` | `colony.failed` | Colony failed |

### Run Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `RUN_STARTED` | `run.started` | A Run was started |
| `RUN_COMPLETED` | `run.completed` | Run finished successfully |
| `RUN_FAILED` | `run.failed` | Run failed |
| `RUN_ABORTED` | `run.aborted` | Run was aborted (emergency stop) |

### Task Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `TASK_CREATED` | `task.created` | A Task was created |
| `TASK_ASSIGNED` | `task.assigned` | Task was assigned to an agent |
| `TASK_PROGRESSED` | `task.progressed` | Task progress was reported |
| `TASK_COMPLETED` | `task.completed` | Task finished successfully |
| `TASK_FAILED` | `task.failed` | Task failed |
| `TASK_BLOCKED` | `task.blocked` | Task is blocked by a dependency |
| `TASK_UNBLOCKED` | `task.unblocked` | Task blocker was resolved |

### Requirement Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `REQUIREMENT_CREATED` | `requirement.created` | Approval request created |
| `REQUIREMENT_APPROVED` | `requirement.approved` | Requirement was approved |
| `REQUIREMENT_REJECTED` | `requirement.rejected` | Requirement was rejected |

### Decision Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `DECISION_RECORDED` | `decision.recorded` | A decision was recorded |
| `PROPOSAL_CREATED` | `decision.proposal.created` | A proposal was created |
| `DECISION_APPLIED` | `decision.applied` | A decision was applied |
| `DECISION_SUPERSEDED` | `decision.superseded` | A decision was superseded |

### Conference Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `CONFERENCE_STARTED` | `conference.started` | Multi-Colony conference began |
| `CONFERENCE_ENDED` | `conference.ended` | Conference ended |

### Conflict Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `CONFLICT_DETECTED` | `conflict.detected` | A conflict was detected |
| `CONFLICT_RESOLVED` | `conflict.resolved` | A conflict was resolved |

### Intervention Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `USER_DIRECT_INTERVENTION` | `intervention.user_direct` | User bypassed normal flow |
| `QUEEN_ESCALATION` | `intervention.queen_escalation` | Queen Bee escalated to user |
| `BEEKEEPER_FEEDBACK` | `intervention.beekeeper_feedback` | Improvement feedback recorded |

### Worker Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `WORKER_ASSIGNED` | `worker.assigned` | Worker Bee received a task |
| `WORKER_STARTED` | `worker.started` | Worker Bee started work |
| `WORKER_PROGRESS` | `worker.progress` | Worker Bee progress update |
| `WORKER_COMPLETED` | `worker.completed` | Worker Bee finished |
| `WORKER_FAILED` | `worker.failed` | Worker Bee failed |

### LLM Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `LLM_REQUEST` | `llm.request` | LLM API call sent |
| `LLM_RESPONSE` | `llm.response` | LLM API response received |

### Sentinel Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `SENTINEL_ALERT_RAISED` | `sentinel.alert_raised` | Sentinel detected an anomaly |
| `SENTINEL_REPORT` | `sentinel.report` | Sentinel status report |
| `SENTINEL_ROLLBACK` | `sentinel.rollback` | Sentinel triggered rollback |
| `SENTINEL_QUARANTINE` | `sentinel.quarantine` | Sentinel quarantined a resource |
| `SENTINEL_KPI_DEGRADATION` | `sentinel.kpi_degradation` | KPI degradation detected |

### Waggle Dance Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `WAGGLE_DANCE_VALIDATED` | `waggle_dance.validated` | I/O structure validation passed |
| `WAGGLE_DANCE_VIOLATION` | `waggle_dance.violation` | I/O structure violation detected |

### Guard Bee Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `GUARD_VERIFICATION_REQUESTED` | `guard.verification_requested` | Quality verification requested |
| `GUARD_PASSED` | `guard.passed` | Verification passed |
| `GUARD_CONDITIONAL_PASSED` | `guard.conditional_passed` | Passed with conditions |
| `GUARD_FAILED` | `guard.failed` | Verification failed |

### GitHub Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `GITHUB_ISSUE_CREATED` | `github.issue_created` | GitHub Issue created |
| `GITHUB_ISSUE_UPDATED` | `github.issue_updated` | GitHub Issue updated |
| `GITHUB_ISSUE_CLOSED` | `github.issue_closed` | GitHub Issue closed |
| `GITHUB_COMMENT_ADDED` | `github.comment_added` | GitHub comment added |
| `GITHUB_LABEL_APPLIED` | `github.label_applied` | GitHub label applied |
| `GITHUB_PROJECT_SYNCED` | `github.project_synced` | GitHub project synced |

### Operation Events

| Event Type | Value | Description |
|-----------|-------|-------------|
| `OPERATION_TIMEOUT` | `operation.timeout` | Operation timed out |
| `OPERATION_FAILED` | `operation.failed` | Operation failed |

## Auto-generated Reference

::: hiveforge.core.events.types.EventType
    options:
      show_root_heading: true
      members_order: source
