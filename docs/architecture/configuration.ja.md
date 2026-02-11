# 設定

HiveForgeはプロジェクトルートの `hiveforge.config.yaml` で設定します。

環境変数による上書きは `HIVEFORGE_<セクション>__<キー>` のパターンに従います（例: `HIVEFORGE_SERVER__PORT=9000`）。

## 設定セクション

### `hive` — プロジェクト設定

```yaml
hive:
  name: "my-project"           # プロジェクト名（Hive識別用）
  vault_path: "./Vault"        # イベントログ保存ディレクトリ
```

### `server` — APIサーバー

```yaml
server:
  host: "0.0.0.0"              # バインドホスト
  port: 8000                   # リッスンポート
```

### `governance` — エージェントガバナンス

```yaml
governance:
  max_retries: 3                    # タスク失敗時の最大リトライ回数
  max_oscillations: 5               # ループ検知しきい値
  max_concurrent_tasks: 10          # 同時実行可能タスク数
  task_timeout_seconds: 300         # タスクタイムアウト（秒）
  heartbeat_interval_seconds: 30    # ハートビート間隔
  approval_timeout_hours: 24        # ユーザー承認待ちタイムアウト（時間）
  archive_after_days: 7             # 完了Runをアーカイブするまでの日数
```

### `llm` — LLMプロバイダー

LiteLLM SDK経由で100以上のプロバイダーをサポート。

```yaml
llm:
  provider: "openai"              # プロバイダー名
  model: "gpt-4o"                 # モデル名
  api_key_env: "OPENAI_API_KEY"   # APIキーの環境変数名
  max_tokens: 4096
  temperature: 0.2
  rate_limit:
    requests_per_minute: 60
    requests_per_day: 0           # 0 = 無制限
    tokens_per_minute: 90000
    max_concurrent: 10
    burst_limit: 10
    retry_after_429: 60
```

#### Ollama（ローカルLLM）設定例

```yaml
llm:
  provider: "ollama_chat"
  model: "qwen3-coder"
  api_base: "http://localhost:11434"
  max_tokens: 4096
  temperature: 0.2
```

### `auth` — 認証

```yaml
auth:
  enabled: false
  api_key_env: "HIVEFORGE_API_KEY"
```

### `agents` — エージェント設定

各エージェントはグローバルLLM設定を個別に上書きできます。

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

### `sentinel` — Sentinel Hornet（安全監視）

```yaml
sentinel:
  enabled: true
  max_event_rate: 50            # レートウィンドウ内の最大イベント数
  rate_window_seconds: 60
  max_loop_count: 5             # ループ検知しきい値
  max_cost: 100.0               # 最大コスト（ドル）
  auto_suspend: true            # critical時にColonyを自動一時停止
```

### `swarming` — Swarming Protocol（適応的編成）

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

### `conflict` — 衝突検出

```yaml
conflict:
  detection_enabled: true
  auto_resolve_low_severity: true
  escalation_timeout_minutes: 30
```

### `conference` — 複数Colony会議

```yaml
conference:
  enabled: true
  max_participants: 10
  voting_timeout_minutes: 15
  quorum_percentage: 50         # 議決に必要な定足数（%）
```

### `logging` — ロギング

```yaml
logging:
  level: "INFO"                 # DEBUG | INFO | WARNING | ERROR
  events_max_file_size_mb: 100
```

### プロンプト設定

エージェントのプロンプトはYAMLファイルで管理され、階層的に検索されます：

1. `Vault/hives/{hive_id}/colonies/{colony_id}/` — Colony固有
2. `Vault/hives/{hive_id}/` — Hive全体のデフォルト
3. `src/hiveforge/prompts/defaults/` — パッケージ内デフォルト
4. ハードコードフォールバック

ファイル命名規則：

| ファイル | 用途 |
|---------|------|
| `beekeeper.yml` | Beekeeperプロンプト |
| `queen_bee.yml` | Queen Beeプロンプト |
| `{name}_worker_bee.yml` | 名前付きWorker Bee |
| `default_worker_bee.yml` | デフォルトWorker Bee |
