# MCP Tools

ColonyForge exposes tools via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) for use in GitHub Copilot Chat.

## Setup

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "colonyforge": {
      "command": "colonyforge",
      "args": ["mcp"],
      "env": {}
    }
  }
}
```

Then reload VS Code (Command Palette → **Developer: Reload Window**).

Use `@colonyforge` in Copilot Chat to access tools.

## Tool Reference

### Hive / Colony Management

| Tool | Description |
|------|-------------|
| `create_hive` | Create a new Hive (project-level unit) |
| `list_hives` | List all Hives |
| `get_hive` | Get Hive details and status |
| `close_hive` | Close a Hive |
| `create_colony` | Create a Colony within a Hive |
| `list_colonies` | List Colonies in a Hive |
| `start_colony` | Start a Colony |
| `complete_colony` | Complete a Colony |

### Run / Task Operations

| Tool | Description |
|------|-------------|
| `start_run` | Start a new Run with a goal |
| `get_run_status` | Get Run progress, tasks, and next actions |
| `create_task` | Create a Task in a Run |
| `assign_task` | Assign a Task and start working |
| `report_progress` | Report Task progress (0–100%) |
| `complete_task` | Mark a Task as completed with results |
| `fail_task` | Mark a Task as failed with error details |
| `complete_run` | Complete the Run |
| `heartbeat` | Send heartbeat to prevent silence detection |
| `emergency_stop` | Emergency stop a Run |

### Decision / Tracing

| Tool | Description |
|------|-------------|
| `record_decision` | Record a Decision event (D-key, rationale, options) |
| `get_lineage` | Get causal links for any event |

### Conference

| Tool | Description |
|------|-------------|
| `start_conference` | Start a multi-Colony conference |
| `end_conference` | End conference with summary and decisions |
| `list_conferences` | List conferences |
| `get_conference` | Get conference details |

### Quality Verification

| Tool | Description |
|------|-------------|
| `verify_colony` | Run Guard Bee L1/L2 verification with evidence |
| `get_guard_report` | Get Guard Bee verification reports for a Run |

### Approval / Requirements

| Tool | Description |
|------|-------------|
| `create_requirement` | Create a user approval request |
| `approve` | Approve a pending operation |
| `reject` | Reject a pending operation |

### Intervention / Escalation

| Tool | Description |
|------|-------------|
| `user_intervene` | Direct user intervention (bypasses Beekeeper) |
| `queen_escalate` | Queen Bee escalation to user |
| `beekeeper_feedback` | Record Beekeeper feedback after intervention |
| `list_escalations` | List all escalations |
| `get_escalation` | Get escalation details |

### Beekeeper

| Tool | Description |
|------|-------------|
| `send_message` | Send message to Beekeeper |
| `get_beekeeper_status` | Get Hive/Colony status via Beekeeper |

### GitHub Integration

| Tool | Description |
|------|-------------|
| `sync_run_to_github` | Sync Run events to GitHub Issues/Comments/Labels (idempotent) |
| `get_github_sync_status` | Get GitHub Projection sync status |
