# CLI Reference

HiveForge provides a command-line interface for server management, task execution, and interactive sessions.

## Synopsis

```
hiveforge <command> [options]
```

## Commands

### `server` — Start API Server

Starts the FastAPI REST server.

```bash
hiveforge server [--host HOST] [--port PORT] [--reload]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind host address |
| `--port` | `8000` | Port number |
| `--reload` | off | Enable hot-reload for development |

**Example:**

```bash
hiveforge server --port 8080 --reload
```

After starting, Swagger UI is available at `http://localhost:8000/docs`.

---

### `mcp` — Start MCP Server

Starts the Model Context Protocol server for GitHub Copilot Chat integration.

```bash
hiveforge mcp
```

Communication uses **stdio**. Configure in `.vscode/mcp.json`:

```json
{
  "servers": {
    "hiveforge": {
      "command": "hiveforge",
      "args": ["mcp"]
    }
  }
}
```

---

### `init` — Initialize Project

Creates a new Hive scaffolding.

```bash
hiveforge init [--name NAME]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--name` | `my-hive` | Hive name |

---

### `status` — Show Run Status

Displays the current state of a Run.

```bash
hiveforge status [--run-id RUN_ID]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--run-id` | (latest) | Run ID. Omit for the most recent Run |

---

### `run` — Execute Task with LLM

Runs a task using an LLM agent in a single pass.

```bash
hiveforge run "task description" [--agent AGENT]
```

| Option | Default | Choices | Description |
|--------|---------|---------|-------------|
| `--agent` | `worker_bee` | `worker_bee`, `queen_bee`, `beekeeper` | Agent to use |

**Example:**

```bash
hiveforge run "Create a REST endpoint for user authentication" --agent queen_bee
```

---

### `chat` — Interactive Chat with Beekeeper

Sends a message to the Beekeeper agent for interactive dialogue.

```bash
hiveforge chat "message"
```

**Example:**

```bash
hiveforge chat "What is the status of the current project?"
```

---

### `record-decision` — Record a Decision

Records a Decision event to the Akashic Record.

```bash
hiveforge record-decision \
  --key D5 \
  --title "Choose database engine" \
  --selected "PostgreSQL" \
  [--run-id RUN_ID] \
  [--rationale "..."] \
  [--impact "..."] \
  [--option "Option A" --option "Option B"] \
  [--supersedes D3]
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--key` | Yes | — | Decision key (e.g., `D5`) |
| `--title` | Yes | — | Decision title |
| `--selected` | Yes | — | Selected option |
| `--run-id` | No | `meta-decisions` | Run ID to store the decision |
| `--rationale` | No | `""` | Reasoning |
| `--impact` | No | `""` | Impact scope |
| `--option` | No | `[]` | Options considered (repeatable) |
| `--supersedes` | No | `[]` | Decision keys this supersedes (repeatable) |
