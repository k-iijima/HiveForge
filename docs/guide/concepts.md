# Concepts

## Hierarchical Model

ColonyForge organizes work in a 4-level hierarchy:

```mermaid
graph TD
    H[Hive - Project] --> C1[Colony - UI/UX]
    H --> C2[Colony - API]
    H --> C3[Colony - Infrastructure]
    C1 --> R1[Run 1]
    C1 --> R2[Run 2]
    C2 --> R3[Run 3]
    R1 --> T1[Task 1]
    R1 --> T2[Task 2]
    R3 --> T3[Task 3]
```

### Hive

A **Hive** is the top-level organizational unit, representing a project or initiative.

- Contains multiple Colonies
- Managed by the Beekeeper agent
- States: `active` → `closed`

### Colony

A **Colony** is a specialized work group within a Hive, focused on a particular domain (e.g., UI, API, infrastructure).

- Contains multiple Runs
- Managed by the Queen Bee agent
- States: `pending` → `active` → `completed` / `failed`

### Run

A **Run** represents a single execution pass of work. All state changes within a Run are recorded as events.

- Contains Tasks and Requirements
- States: `running` → `completed` / `stopped` / `failed` / `timed_out`

### Task

A **Task** is an atomic unit of work within a Run.

- States: `pending` → `in_progress` → `completed` / `failed` / `cancelled`
- Each task records its result upon completion

### Requirement (Approval Request)

A **Requirement** represents a confirmation request that needs user approval before proceeding.

- States: `pending` → `approved` / `rejected` / `cancelled`
- Governed by ActionClass and TrustLevel

## Event Sourcing

All state changes in ColonyForge are recorded as **immutable events** in the Akashic Record (AR).

```mermaid
sequenceDiagram
    participant User
    participant API
    participant AR as Akashic Record

    User->>API: POST /runs
    API->>AR: Append RunStarted event
    API-->>User: Run ID

    User->>API: POST /runs/{id}/tasks
    API->>AR: Append TaskCreated event
    API-->>User: Task ID

    User->>API: POST /tasks/{id}/complete
    API->>AR: Append TaskCompleted event
    API-->>User: OK
```

### Event Properties

Every event includes:

| Field | Description |
|-------|-------------|
| `event_id` | Unique ID (ULID — time-ordered) |
| `run_id` | Owning Run |
| `event_type` | Type enum (e.g., `RUN_STARTED`, `TASK_COMPLETED`) |
| `timestamp` | ISO 8601 timestamp |
| `hash` | SHA-256 hash of canonical JSON (JCS) |
| `parent_hash` | Previous event's hash — forms a chain |

### Causal Tracing (Lineage)

Events can be linked causally, allowing you to trace "why" any artifact was produced.

```
TaskCompleted → linked to → TaskCreated → linked to → RunStarted
```

Use `GET /runs/{run_id}/events/{event_id}/lineage` to explore the causal graph.

## State Machines

Each entity follows a strict state machine. Invalid transitions raise errors immediately (fail-fast).

### Run States

```mermaid
stateDiagram-v2
    [*] --> running: start
    running --> completed: complete (all tasks done)
    running --> stopped: emergency_stop
    running --> failed: fail
    running --> timed_out: timeout
```

### Task States

```mermaid
stateDiagram-v2
    [*] --> pending: create
    pending --> in_progress: assign
    in_progress --> completed: complete
    in_progress --> failed: fail
    pending --> cancelled: cancel
    in_progress --> cancelled: cancel
```

## ActionClass and Trust Levels

Operations are classified by risk level:

| ActionClass | Examples | Approval |
|-------------|----------|----------|
| `SAFE` | Read files, search | Auto-approved |
| `NORMAL` | Create files, run tests | Based on trust level |
| `DANGEROUS` | Delete files, exec commands | Requires approval |
| `CRITICAL` | Deploy, data migration | Always requires approval |

Trust levels (`UNTRUSTED`, `BASIC`, `TRUSTED`, `ADMIN`) determine the approval threshold.

## Honeycomb (Learning)

The Honeycomb system records execution **Episodes** — snapshots of a Colony's performance — and calculates KPIs:

| KPI | Description |
|-----|-------------|
| Correctness | Tasks completed without failures |
| Guard Pass Rate | Quality verification pass rate |
| Repeatability | Consistency across multiple runs |
| Avg Cycle Time | Average task completion time |
| Collaboration Score | Cross-colony coordination quality |

These KPIs enable improvement cycles (PDCA) by tracking trends over time.
