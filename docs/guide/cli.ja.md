# CLIリファレンス

ColonyForgeはサーバー管理、タスク実行、対話セッション用のコマンドラインインターフェースを提供します。

## 文法

```
colonyforge <command> [options]
```

## コマンド

### `server` — APIサーバー起動

FastAPI RESTサーバーを起動します。

```bash
colonyforge server [--host HOST] [--port PORT] [--reload]
```

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--host` | `0.0.0.0` | バインドするホストアドレス |
| `--port` | `8000` | ポート番号 |
| `--reload` | オフ | 開発用ホットリロードを有効化 |

**例:**

```bash
colonyforge server --port 8080 --reload
```

起動後、Swagger UIは `http://localhost:8000/docs` で利用できます。

---

### `mcp` — MCPサーバー起動

GitHub Copilot Chat統合用のModel Context Protocolサーバーを起動します。

```bash
colonyforge mcp
```

通信は**stdio**を使用します。`.vscode/mcp.json` で設定：

```json
{
  "servers": {
    "colonyforge": {
      "command": "colonyforge",
      "args": ["mcp"]
    }
  }
}
```

---

### `init` — プロジェクト初期化

新しいHiveのスキャフォールディングを作成します。

```bash
colonyforge init [--name NAME]
```

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--name` | `my-hive` | Hive名 |

---

### `status` — Run状態表示

Runの現在の状態を表示します。

```bash
colonyforge status [--run-id RUN_ID]
```

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--run-id` | （最新） | Run ID。省略時は最新のRun |

---

### `run` — LLMでタスク実行

LLMエージェントを使用してタスクをワンパスで実行します。

```bash
colonyforge run "タスクの説明" [--agent AGENT]
```

| オプション | デフォルト | 選択肢 | 説明 |
|-----------|----------|--------|------|
| `--agent` | `worker_bee` | `worker_bee`, `queen_bee`, `beekeeper` | 使用するエージェント |

**例:**

```bash
colonyforge run "ユーザー認証用のRESTエンドポイントを作成" --agent queen_bee
```

---

### `chat` — Beekeeperとの対話

Beekeeperエージェントにメッセージを送信し対話します。

```bash
colonyforge chat "メッセージ"
```

**例:**

```bash
colonyforge chat "現在のプロジェクトの状況は？"
```

---

### `record-decision` — Decisionの記録

Akashic RecordにDecisionイベントを記録します。

```bash
colonyforge record-decision \
  --key D5 \
  --title "データベースエンジンの選択" \
  --selected "PostgreSQL" \
  [--run-id RUN_ID] \
  [--rationale "..."] \
  [--impact "..."] \
  [--option "選択肢A" --option "選択肢B"] \
  [--supersedes D3]
```

| オプション | 必須 | デフォルト | 説明 |
|-----------|------|----------|------|
| `--key` | はい | — | Decisionキー（例: `D5`） |
| `--title` | はい | — | Decisionタイトル |
| `--selected` | はい | — | 選択した案 |
| `--run-id` | いいえ | `meta-decisions` | Decisionを格納するRun ID |
| `--rationale` | いいえ | `""` | 理由 |
| `--impact` | いいえ | `""` | 影響範囲 |
| `--option` | いいえ | `[]` | 検討した選択肢（繰り返し指定可） |
| `--supersedes` | いいえ | `[]` | 置き換えるDecisionキー（繰り返し指定可） |
