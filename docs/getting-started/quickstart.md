# Quick Start

Get ColonyForge running and complete your first workflow in 5 minutes.

## 1. Start the API Server

Press **F5** in VS Code (with devcontainer), or:

```bash
colonyforge server
```

Open Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

## 2. Create a Hive

A Hive represents a project — the top-level organizational unit.

```bash
curl -X POST http://localhost:8000/hives \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project", "description": "First ColonyForge project"}'
```

## 3. Create a Colony

A Colony is a specialized work group within a Hive.

```bash
curl -X POST http://localhost:8000/hives/{hive_id}/colonies \
  -H "Content-Type: application/json" \
  -d '{"name": "Feature A", "goal": "Implement feature A"}'

# Start the colony
curl -X POST http://localhost:8000/colonies/{colony_id}/start
```

## 4. Start a Run

A Run represents a single execution pass of work.

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "Implement login feature"}'
```

## 5. Create and Complete Tasks

```bash
# Create a task
curl -X POST http://localhost:8000/runs/{run_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Create login form", "description": "HTML/CSS login form"}'

# Complete the task
curl -X POST http://localhost:8000/runs/{run_id}/tasks/{task_id}/complete \
  -H "Content-Type: application/json" \
  -d '{"result": "Login form created"}'
```

## 6. Complete the Run

```bash
curl -X POST http://localhost:8000/runs/{run_id}/complete
```

!!! tip
    If there are uncompleted tasks, use `{"force": true}` to force completion (auto-cancels remaining tasks and requirements).

## 7. View in VS Code

Install the ColonyForge extension to see:

- **Hive Monitor** — Webview dashboard with KPI gauges
- **Event Log** — TreeView of all events
- **Status Bar** — Current Run status

## Using MCP (GitHub Copilot Chat)

Configure `.vscode/mcp.json`:

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

Then use `@colonyforge` in Copilot Chat to operate ColonyForge directly.

## Next Steps

- [Concepts](../guide/concepts.md) — Understand the Hive/Colony/Run/Task model
- [CLI Reference](../guide/cli.md) — All CLI commands
- [Agents](../guide/agents.md) — Learn about each agent's role
