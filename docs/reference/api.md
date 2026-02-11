# REST API Reference

HiveForge provides a FastAPI-based REST API. Full interactive documentation is available at `http://localhost:8000/docs` (Swagger UI) when the server is running.

## Base URL

```
http://localhost:8000
```

## Endpoints Overview

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/openapi.json` | OpenAPI specification |

### Runs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/runs` | Start a new Run |
| GET | `/runs` | List all Runs |
| GET | `/runs/{run_id}` | Get Run details |
| POST | `/runs/{run_id}/complete` | Complete a Run |
| POST | `/runs/{run_id}/emergency-stop` | Emergency stop a Run |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/runs/{run_id}/tasks` | Create a Task |
| GET | `/runs/{run_id}/tasks` | List Tasks in a Run |
| POST | `/runs/{run_id}/tasks/{task_id}/assign` | Assign a Task |
| POST | `/runs/{run_id}/tasks/{task_id}/complete` | Complete a Task |
| POST | `/runs/{run_id}/tasks/{task_id}/fail` | Fail a Task |
| POST | `/runs/{run_id}/tasks/{task_id}/progress` | Report Task progress |

### Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/runs/{run_id}/events` | List events in a Run |
| GET | `/runs/{run_id}/events/{event_id}/lineage` | Get event lineage |

### Requirements (Approval)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/runs/{run_id}/requirements` | Create a requirement |
| POST | `/runs/{run_id}/requirements/{req_id}/approve` | Approve |
| POST | `/runs/{run_id}/requirements/{req_id}/reject` | Reject |

### Hives

| Method | Path | Description |
|--------|------|-------------|
| POST | `/hives` | Create a Hive |
| GET | `/hives` | List Hives |
| GET | `/hives/{hive_id}` | Get Hive details |
| POST | `/hives/{hive_id}/close` | Close a Hive |

### Colonies

| Method | Path | Description |
|--------|------|-------------|
| POST | `/hives/{hive_id}/colonies` | Create a Colony |
| GET | `/hives/{hive_id}/colonies` | List Colonies |
| POST | `/colonies/{colony_id}/start` | Start a Colony |
| POST | `/colonies/{colony_id}/complete` | Complete a Colony |

### Conferences

| Method | Path | Description |
|--------|------|-------------|
| POST | `/conferences` | Start a conference |
| GET | `/conferences` | List conferences |
| GET | `/conferences/{conf_id}` | Get conference details |
| POST | `/conferences/{conf_id}/end` | End a conference |

### Guard Bee (Quality Verification)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/guard-bee/verify` | Submit verification with evidence |
| GET | `/guard-bee/reports/{run_id}` | Get verification reports |

### KPI / Honeycomb

| Method | Path | Description |
|--------|------|-------------|
| GET | `/kpi/evaluation` | Get KPI evaluation summary |
| GET | `/kpi/episodes` | List recorded episodes |

### Interventions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/interventions/user-intervene` | Direct user intervention |
| POST | `/interventions/queen-escalate` | Queen Bee escalation |
| POST | `/interventions/beekeeper-feedback` | Record feedback |
| GET | `/interventions/escalations` | List escalations |
| GET | `/interventions/escalations/{esc_id}` | Get escalation details |

### Beekeeper

| Method | Path | Description |
|--------|------|-------------|
| POST | `/beekeeper/message` | Send message to Beekeeper |
| GET | `/beekeeper/status` | Get Beekeeper status |

### Activity Feed

| Method | Path | Description |
|--------|------|-------------|
| GET | `/activities` | Get activity feed |

## Auto-generated Module Reference

### Events

::: hiveforge.core.events.base
    options:
      show_root_heading: true
      members_order: source

::: hiveforge.core.events.types
    options:
      show_root_heading: true
      members_order: source

### Akashic Record

::: hiveforge.core.ar.storage
    options:
      show_root_heading: true
      members_order: source

### Honeycomb

::: hiveforge.core.honeycomb.kpi
    options:
      show_root_heading: true
      members_order: source

::: hiveforge.core.honeycomb.models
    options:
      show_root_heading: true
      members_order: source

### Domain Models

::: hiveforge.core.models.action_class
    options:
      show_root_heading: true
      members_order: source
