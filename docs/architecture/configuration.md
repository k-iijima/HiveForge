# Configuration

HiveForge is configured via `hiveforge.config.yaml` at the project root.

Environment variable overrides follow the pattern: `HIVEFORGE_<SECTION>__<KEY>` (e.g., `HIVEFORGE_SERVER__PORT=9000`).

## Configuration Sections

### `hive` — Project Settings

```yaml
hive:
  name: "my-project"           # Project name (Hive identifier)
  vault_path: "./Vault"        # Event log storage directory
```

### `server` — API Server

```yaml
server:
  host: "0.0.0.0"              # Bind host
  port: 8000                   # Listen port
```

### `governance` — Agent Governance

```yaml
governance:
  max_retries: 3                    # Max retries on task failure
  max_oscillations: 5               # Loop detection threshold
  max_concurrent_tasks: 10          # Max concurrent tasks
  task_timeout_seconds: 300         # Task timeout (seconds)
  heartbeat_interval_seconds: 30    # Heartbeat interval
  approval_timeout_hours: 24        # User approval timeout (hours)
  archive_after_days: 7             # Days before archiving completed Runs
```

### `llm` — LLM Provider

Supports 100+ providers via LiteLLM SDK.

```yaml
llm:
  provider: "openai"              # Provider name
  model: "gpt-4o"                 # Model name
  api_key_env: "OPENAI_API_KEY"   # Environment variable for API key
  max_tokens: 4096
  temperature: 0.2
  rate_limit:
    requests_per_minute: 60
    requests_per_day: 0           # 0 = unlimited
    tokens_per_minute: 90000
    max_concurrent: 10
    burst_limit: 10
    retry_after_429: 60
```

#### Ollama (Local LLM) Example

```yaml
llm:
  provider: "ollama_chat"
  model: "qwen3-coder"
  api_base: "http://localhost:11434"
  max_tokens: 4096
  temperature: 0.2
```

### `auth` — Authentication

```yaml
auth:
  enabled: false
  api_key_env: "HIVEFORGE_API_KEY"
```

### `agents` — Agent Configuration

Each agent can override the global LLM settings.

```yaml
agents:
  beekeeper:
    enabled: true
    max_colonies: 10
    session_timeout_minutes: 60

  queen_bee:
    enabled: true
    max_workers_per_colony: 5
    task_assignment_strategy: "round_robin"  # round_robin | priority | load_balanced

  worker_bee:
    enabled: true
    tool_timeout_seconds: 60
    max_retries: 3
    trust_level_default: "standard"  # untrusted | limited | standard | elevated | full
```

### `sentinel` — Sentinel Hornet (Safety Monitor)

```yaml
sentinel:
  enabled: true
  max_event_rate: 50            # Max events per rate window
  rate_window_seconds: 60
  max_loop_count: 5             # Loop detection threshold
  max_cost: 100.0               # Max cost (USD)
  auto_suspend: true            # Auto-suspend Colony on critical alert
```

### `swarming` — Swarming Protocol (Adaptive Formation)

```yaml
swarming:
  enabled: true
  default_template: "balanced"  # speed | balanced | quality | recovery
  templates:
    speed:
      min_workers: 1
      max_workers: 1
      guard_bee: false
    balanced:
      min_workers: 2
      max_workers: 3
      guard_bee: true
    quality:
      min_workers: 3
      max_workers: 5
      guard_bee: true
      reviewer: true
    recovery:
      min_workers: 1
      max_workers: 2
      guard_bee: true
```

### `conflict` — Conflict Detection

```yaml
conflict:
  detection_enabled: true
  auto_resolve_low_severity: true
  escalation_timeout_minutes: 30
```

### `conference` — Multi-Colony Conference

```yaml
conference:
  enabled: true
  max_participants: 10
  voting_timeout_minutes: 15
  quorum_percentage: 50         # Quorum required for decisions
```

### `logging` — Logging

```yaml
logging:
  level: "INFO"                 # DEBUG | INFO | WARNING | ERROR
  events_max_file_size_mb: 100
```

### Prompt Configuration

Agent prompts are managed via YAML files with a hierarchical lookup:

1. `Vault/hives/{hive_id}/colonies/{colony_id}/` — Colony-specific
2. `Vault/hives/{hive_id}/` — Hive-wide defaults
3. `src/hiveforge/prompts/defaults/` — Package defaults
4. Hardcoded fallback

File naming conventions:

| File | Purpose |
|------|---------|
| `beekeeper.yml` | Beekeeper prompt |
| `queen_bee.yml` | Queen Bee prompt |
| `{name}_worker_bee.yml` | Named Worker Bee |
| `default_worker_bee.yml` | Default Worker Bee |
