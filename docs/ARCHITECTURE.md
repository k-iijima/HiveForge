# HiveForge アーキテクチャ設計書

このドキュメントでは、HiveForgeの現在の設計と実装状況を説明します。

---

## 目次

1. [システム概要](#1-システム概要)
2. [コンポーネント構成](#2-コンポーネント構成)
3. [データモデル](#3-データモデル)
4. [API仕様](#4-api仕様)
5. [状態機械](#5-状態機械)
6. [イベントシステム](#6-イベントシステム)
7. [因果リンク（Lineage）](#7-因果リンクlineage)
8. [ディレクトリ構造](#8-ディレクトリ構造)
9. [設定](#9-設定)
10. [フェーズゲート条件](#10-フェーズゲート条件)
11. [今後の拡張](#11-今後の拡張)

---

## 1. システム概要

### 1.1 基本思想

HiveForgeは「**信頼できる部品を、信頼できる組み合わせ方をして、信頼できるシステムを作る**」という理念に基づいています。

### 1.2 コア原則

- **イベントソーシング**: 全ての状態変更をイベントとして記録
- **イミュータブル**: イベントは一度書き込まれたら変更不可
- **追跡可能性**: 任意の成果物から「なぜ」を遡及可能
- **制御可能性**: 状態機械による厳密な状態管理と緊急停止

### 1.3 アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────┐
│                         VS Code                              │
│  ┌──────────────────┐  ┌────────────────────────────────┐   │
│  │  GitHub Copilot  │  │  HiveForge Extension           │   │
│  │      Chat        │  │  ├─ ダッシュボード (Webview)    │   │
│  │  （対話・操作）   │  │  ├─ イベントログ (TreeView)    │   │
│  └────────┬─────────┘  │  └─ ステータスバー             │   │
│           │            └────────────────┬───────────────┘   │
└───────────┼─────────────────────────────┼───────────────────┘
            │ MCP                         │ HTTP
            ▼                             ▼
┌───────────────────────┐    ┌─────────────────────────────┐
│  HiveForge MCP Server │    │    HiveForge API Server     │
│  (stdio通信)          │    │    (FastAPI / REST)         │
└───────────┬───────────┘    └──────────────┬──────────────┘
            │                               │
            └──────────────┬────────────────┘
                           ▼
            ┌──────────────────────────────┐
            │         Hive Core            │
            │  ┌────────────────────────┐  │
            │  │   Akashic Record (AR)  │  │
            │  │   - イベント永続化     │  │
            │  │   - ハッシュ連鎖       │  │
            │  └────────────────────────┘  │
            │  ┌────────────────────────┐  │
            │  │    State Machines      │  │
            │  │   - Run / Task / Req   │  │
            │  └────────────────────────┘  │
            │  ┌────────────────────────┐  │
            │  │     Projections        │  │
            │  │   - イベント→状態     │  │
            │  └────────────────────────┘  │
            └──────────────────────────────┘
                           │
                           ▼
            ┌──────────────────────────────┐
            │      Vault (ファイルシステム)  │
            │  └── {run_id}/events.jsonl   │
            └──────────────────────────────┘
```

---

## 2. コンポーネント構成

### 2.1 コンポーネント一覧

| コンポーネント | 役割 | 実装状況 |
|----------------|------|----------|
| **Hive Core** | イベント管理・状態機械・投影 | ✅ 完了 |
| **API Server** | REST API エンドポイント | ✅ 完了 |
| **MCP Server** | Copilot Chat連携 | ✅ 完了 |
| **CLI** | コマンドラインインターフェース | ✅ 完了 |
| **VS Code拡張** | ダッシュボード・可視化 | ✅ 完了（テスト付き） |
| **Agent UI** | ブラウザ自動操作MCPサーバー | ✅ 完了 |
| **VLM** | 画像解析・画面認識 | ✅ 完了 |
| **VLM Tester** | Playwright + VLMによるE2Eテスト | ✅ 完了 |
| **Silence Detector** | 沈黙検出 | ✅ 完了 |

### 2.2 モジュール依存関係

```
hiveforge/
├── core/                  # コアモジュール（他から参照される）
│   ├── events.py         # イベントモデル
│   ├── config.py         # 設定管理
│   ├── ar/               # Akashic Record
│   │   ├── storage.py    # 永続化
│   │   └── projections.py # 状態投影
│   └── state/            # 状態機械
│       └── machines.py   # Run/Task/Requirement SM
├── api/                   # REST API（coreに依存）
│   ├── server.py         # FastAPIアプリ
│   ├── dependencies.py   # 依存性注入（AppState）
│   ├── helpers.py        # 後方互換エクスポート
│   └── routes/           # エンドポイント
│       ├── runs.py       # Run関連
│       ├── tasks.py      # Task関連
│       ├── events.py     # Event関連
│       ├── requirements.py # Requirement関連
│       └── system.py     # ヘルスチェック等
├── mcp_server/            # MCP Server（coreに依存）
│   ├── server.py
│   ├── tools.py          # ツール定義
│   └── handlers/         # ハンドラー実装
├── agent_ui/              # Agent UI MCPサーバー
│   ├── server.py         # サーバー本体
│   ├── session.py        # ブラウザセッション管理
│   ├── tools.py          # ツール定義
│   └── handlers.py       # ハンドラー実装
├── vlm/                   # VLM（画像解析）
│   ├── analyzer.py       # 画像分析
│   └── ollama_client.py  # Ollamaクライアント
├── vlm_tester/            # VLM Tester（E2Eテスト支援）
│   ├── server.py         # MCPサーバー
│   ├── playwright_mcp_client.py
│   ├── vlm_client.py
│   └── hybrid_analyzer.py
├── silence.py             # 沈黙検出（coreに依存）
└── cli.py                 # CLI（api, mcp_serverに依存）
```

---

## 3. データモデル

### 3.1 BaseEvent（イベント基底クラス）

すべてのイベントの基底となるイミュータブルなモデル:

```python
class BaseEvent(BaseModel):
    model_config = {"frozen": True}  # イミュータブル
    
    id: str                    # ULID形式のイベントID
    type: EventType            # イベント種別
    timestamp: datetime        # 発生時刻（UTC）
    run_id: str | None         # 関連するRunのID
    task_id: str | None        # 関連するTaskのID
    actor: str                 # イベント発生者
    payload: dict[str, Any]    # イベントペイロード
    prev_hash: str | None      # 前イベントのハッシュ（チェーン用）
    parents: list[str]         # 親イベントのID（因果リンク用）
    
    @computed_field
    def hash(self) -> str:     # JCS正規化 + SHA-256
        ...
```

### 3.2 イベント型一覧

| カテゴリ | イベント型 | 説明 |
|----------|------------|------|
| **Run** | `run.started` | Run開始 |
| | `run.completed` | Run完了 |
| | `run.failed` | Run失敗 |
| | `run.aborted` | Run中断 |
| **Task** | `task.created` | Task作成 |
| | `task.assigned` | Task割り当て |
| | `task.progressed` | 進捗更新 |
| | `task.completed` | Task完了 |
| | `task.failed` | Task失敗 |
| | `task.blocked` | Taskブロック |
| | `task.unblocked` | ブロック解除 |
| **Requirement** | `requirement.created` | 要件作成 |
| | `requirement.approved` | 承認 |
| | `requirement.rejected` | 却下 |
| **LLM** | `llm.request` | LLMリクエスト |
| | `llm.response` | LLMレスポンス |
| **System** | `system.heartbeat` | ハートビート |
| | `system.error` | エラー |
| | `system.silence_detected` | 沈黙検出 |
| | `system.emergency_stop` | 緊急停止 |

### 3.3 RunProjection（状態投影）

イベントから導出される現在状態:

```python
class RunProjection:
    id: str                           # Run ID
    goal: str                         # 目標
    state: RunState                   # 状態
    started_at: datetime | None       # 開始時刻
    completed_at: datetime | None     # 完了時刻
    tasks: dict[str, TaskProjection]  # タスク一覧
    requirements: dict[str, RequirementProjection]  # 要件一覧
    event_count: int                  # イベント数
    last_heartbeat: datetime | None   # 最終ハートビート
```

### 3.4 TaskProjection

```python
class TaskProjection:
    id: str
    title: str
    state: TaskState        # pending/assigned/in_progress/completed/failed/blocked
    progress: int           # 0-100
    assignee: str | None
    retry_count: int
    created_at: datetime
```

---

## 4. API仕様

### 4.1 REST API エンドポイント

#### System

| Method | Path | 説明 |
|--------|------|------|
| GET | `/health` | ヘルスチェック |

#### Runs

| Method | Path | 説明 |
|--------|------|------|
| POST | `/runs` | Run開始 |
| GET | `/runs` | Run一覧取得 |
| GET | `/runs/{run_id}` | Run詳細取得 |
| POST | `/runs/{run_id}/complete` | Run完了 |
| POST | `/runs/{run_id}/emergency-stop` | 緊急停止 |
| POST | `/runs/{run_id}/heartbeat` | ハートビート送信 |

##### Run完了の詳細

`POST /runs/{run_id}/complete` は未完了タスクがある場合は400エラーを返します。

**リクエストボディ:**
```json
{ "force": true }  // オプション
```

**動作:**
- `force=false`（デフォルト）: 未完了タスクがあればエラー
- `force=true`: 未完了タスクを自動キャンセル、未解決の確認要請を自動却下

**レスポンス例:**
```json
{
  "status": "completed",
  "run_id": "01HZZ...",
  "cancelled_task_ids": ["01HZZ..."],
  "cancelled_requirement_ids": ["01HZZ..."]
}
```

##### 緊急停止の詳細

`POST /runs/{run_id}/emergency-stop` はRunを即座に停止します。

**動作:**
- 未完了タスクを全て失敗状態に
- 未解決の確認要請を全て却下
- Runを`ABORTED`状態に遷移

#### Tasks

| Method | Path | 説明 |
|--------|------|------|
| POST | `/runs/{run_id}/tasks` | Task作成 |
| GET | `/runs/{run_id}/tasks` | Task一覧取得 |
| POST | `/runs/{run_id}/tasks/{task_id}/complete` | Task完了 |
| POST | `/runs/{run_id}/tasks/{task_id}/fail` | Task失敗 |

#### Events

| Method | Path | 説明 |
|--------|------|------|
| GET | `/runs/{run_id}/events` | イベント一覧取得 |
| GET | `/runs/{run_id}/events/{event_id}/lineage` | 因果リンク取得 |

### 4.2 MCP ツール一覧

| ツール | 説明 | パラメータ |
|--------|------|------------|
| `start_run` | Run開始 | `goal` |
| `get_run_status` | 状態取得 | `run_id?` |
| `create_task` | Task作成 | `title`, `description?` |
| `assign_task` | Task割り当て | `task_id` |
| `report_progress` | 進捗報告 | `task_id`, `progress`, `message?` |
| `complete_task` | Task完了 | `task_id`, `result?` |
| `fail_task` | Task失敗 | `task_id`, `error`, `retryable?` |
| `create_requirement` | 要件作成 | `description`, `options?` |
| `complete_run` | Run完了 | `summary?`, `force?` |
| `heartbeat` | ハートビート | `message?` |
| `emergency_stop` | 緊急停止 | `reason`, `scope?` |
| `get_lineage` | 因果リンク取得 | `event_id`, `direction?`, `max_depth?` |

---

## 5. 状態機械

### 5.1 RunStateMachine

```
              ┌───────────────────┐
              │      RUNNING      │
              └─────────┬─────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌───────────┐   ┌───────────┐   ┌───────────┐
│ COMPLETED │   │  FAILED   │   │  ABORTED  │
└───────────┘   └───────────┘   └───────────┘
```

| 遷移元 | 遷移先 | トリガーイベント |
|--------|--------|------------------|
| RUNNING | COMPLETED | `run.completed` |
| RUNNING | FAILED | `run.failed` |
| RUNNING | ABORTED | `run.aborted`, `system.emergency_stop` |

### 5.2 TaskStateMachine

```
┌─────────┐                          
│ PENDING │──────────────────────────┐
└────┬────┘                          │
     │ task.assigned                 │
     ▼                               │
┌──────────┐                         │
│ ASSIGNED │                         │
└────┬─────┘                         │
     │ task.progressed               │
     ▼                               │
┌─────────────┐    task.blocked      │
│ IN_PROGRESS │◄───────────────┐     │
└──────┬──────┘                │     │
       │                       │     │
       ├───────────────────────┤     │
       │                       │     │
       ▼                       ▼     │
┌───────────┐           ┌─────────┐  │
│ COMPLETED │           │ BLOCKED │──┘
└───────────┘           └─────────┘
       ▲                       │
       │                       │
       │    ┌──────────┐       │
       └────│  FAILED  │◄──────┘
            └──────────┘
```

### 5.3 RequirementStateMachine

```
┌─────────┐
│ PENDING │
└────┬────┘
     │
     ├──────────────────┐
     │                  │
     ▼                  ▼
┌──────────┐      ┌──────────┐
│ APPROVED │      │ REJECTED │
└──────────┘      └──────────┘
```

---

## 6. イベントシステム

### 6.1 イベント永続化

イベントはJSONL形式でファイルに追記保存:

```
Vault/
└── {run_id}/
    └── events.jsonl    # 1行1イベント
```

### 6.2 ハッシュ連鎖

各イベントは前のイベントのハッシュを保持し、改ざん検知を可能に:

```
event[0] ─hash─▶ event[1] ─hash─▶ event[2] ─hash─▶ ...
           │              │              │
        prev_hash      prev_hash      prev_hash
```

### 6.3 ハッシュ計算

1. イベントデータから`hash`フィールドを除外
2. JCS (RFC 8785) で正規化
3. SHA-256でハッシュ計算

```python
def compute_hash(data: dict[str, Any]) -> str:
    data_for_hash = {k: v for k, v in data.items() if k != "hash"}
    data_for_hash = _serialize_value(data_for_hash)  # datetime等を変換
    canonical = jcs.canonicalize(data_for_hash)
    return hashlib.sha256(canonical).hexdigest()
```

---

## 7. 因果リンク（Lineage）

### 7.1 概要

各イベントは`parents`フィールドで親イベントを参照し、因果関係を記録:

```python
class TaskCreatedEvent(BaseEvent):
    parents: list[str] = ["run_started_event_id"]  # 親イベントのID
```

### 7.2 探索方向

| 方向 | 説明 | 実装方式 |
|------|------|----------|
| `ancestors` | 祖先（親方向） | `parents[]`を再帰的に辿る |
| `descendants` | 子孫（子方向） | 全イベント走査 |
| `both` | 両方向 | 上記の組み合わせ |

### 7.3 APIレスポンス例

```json
{
  "event_id": "01HZZ...",
  "ancestors": ["01HZY...", "01HZX..."],
  "descendants": ["01J00...", "01J01..."],
  "truncated": false
}
```

### 7.4 制限

- `max_depth`: 探索深度制限（デフォルト: 10）
- `truncated`: 制限により切り詰められた場合`true`

---

## 8. ディレクトリ構造

### 8.1 プロジェクト構造

```
HiveForge/
├── src/hiveforge/           # メインパッケージ
│   ├── __init__.py
│   ├── cli.py               # CLIエントリポイント
│   ├── silence.py           # 沈黙検出
│   ├── core/                # コアモジュール
│   │   ├── __init__.py
│   │   ├── config.py        # 設定管理
│   │   ├── events.py        # イベントモデル
│   │   ├── ar/              # Akashic Record
│   │   │   ├── storage.py   # 永続化
│   │   │   └── projections.py # 状態投影
│   │   └── state/           # 状態機械
│   │       └── machines.py
│   ├── api/                 # REST API
│   │   ├── server.py        # FastAPIアプリ
│   │   ├── dependencies.py  # 依存性注入（AppState）
│   │   ├── helpers.py       # 後方互換エクスポート
│   │   └── routes/          # エンドポイント
│   │       ├── runs.py
│   │       ├── tasks.py
│   │       ├── events.py
│   │       ├── requirements.py
│   │       └── system.py
│   ├── mcp_server/          # MCP Server
│   │   ├── server.py
│   │   ├── tools.py         # ツール定義
│   │   └── handlers/        # ハンドラー実装
│   ├── agent_ui/            # Agent UI MCPサーバー
│   │   ├── server.py        # サーバー本体
│   │   ├── session.py       # ブラウザセッション管理
│   │   ├── tools.py         # ツール定義
│   │   └── handlers.py      # ハンドラー実装
│   ├── vlm/                 # VLM（画像解析）
│   │   ├── analyzer.py      # 画像分析
│   │   └── ollama_client.py # Ollamaクライアント
│   └── vlm_tester/          # VLM Tester（E2Eテスト支援）
│       ├── server.py        # MCPサーバー
│       ├── playwright_mcp_client.py
│       ├── vlm_client.py
│       └── hybrid_analyzer.py
├── tests/                   # Pythonテスト（401件）
│   ├── conftest.py
│   ├── test_events.py
│   ├── test_ar.py
│   ├── test_projections.py
│   ├── test_state_machines.py
│   ├── test_silence.py
│   ├── test_cli.py
│   ├── test_api.py
│   ├── test_mcp_server.py
│   ├── test_agent_ui.py
│   ├── test_vlm.py
│   ├── test_vlm_tester.py
│   └── e2e/                 # E2Eテスト
│       ├── test_hiveforge_visual.py
│       └── test_hiveforge_extension.py
├── vscode-extension/        # VS Code拡張
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── extension.ts
│       ├── client.ts        # APIクライアント
│       ├── commands/        # コマンド実装
│       ├── providers/       # TreeViewプロバイダー
│       ├── views/           # Webviewパネル
│       ├── utils/           # ユーティリティ
│       └── test/            # テスト（17件）
│           ├── client.test.ts
│           ├── html.test.ts
│           └── vscode-mock.ts
├── docs/                    # ドキュメント
│   ├── QUICKSTART.md
│   └── ARCHITECTURE.md
├── Vault/                   # イベントログ（gitignore）
├── AGENTS.md                # AI開発ガイドライン
├── docs/コンセプト_v4.md      # コンセプト（作業用仕様・最新版）
├── docs/コンセプト_v3.md      # コンセプト（v3・ベースライン）
├── pyproject.toml           # Pythonプロジェクト設定
├── hiveforge.config.yaml    # 実行時設定
├── docker-compose.yml       # Docker設定
└── Dockerfile
```

### 8.2 Vault構造

```
Vault/
├── {run_id}/
│   └── events.jsonl         # イベントログ（1行1イベント）
└── ...
```

---

## 9. 設定

### 9.1 hiveforge.config.yaml

```yaml
hive:
  name: "poc-project"
  vault_path: "./Vault"

governance:
  max_retries: 3              # タスクの最大リトライ回数
  max_oscillations: 5         # 状態振動検出閾値
  max_concurrent_tasks: 10    # 同時実行タスク数上限
  task_timeout_seconds: 300   # タスクタイムアウト（秒）
  heartbeat_interval_seconds: 30  # ハートビート間隔
  approval_timeout_hours: 24  # 承認待ちタイムアウト
  archive_after_days: 7       # アーカイブ日数

llm:
  provider: "openai"
  model: "gpt-4o"
  api_key_env: "OPENAI_API_KEY"
  max_tokens: 4096
  temperature: 0.2

auth:
  enabled: false              # API認証（POCでは無効）
  api_key_env: "HIVEFORGE_API_KEY"

server:
  host: "0.0.0.0"
  port: 8000

logging:
  level: "INFO"
  events_max_file_size_mb: 100
```

### 9.2 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|------------|
| `HIVEFORGE_VAULT_PATH` | Vaultディレクトリパス | `./Vault` |
| `OPENAI_API_KEY` | OpenAI APIキー | - |
| `HIVEFORGE_API_KEY` | HiveForge API認証キー | - |

---

## 10. フェーズゲート条件

### 10.1 概要

HiveForge の開発はフェーズに分かれており、各フェーズを完了するためには「ゲート条件」を満たす必要があります。これにより、早期フェーズの成果物が安定していることを確認してから次のフェーズに進むことができます。

### 10.2 フェーズ一覧

| フェーズ | 名称 | 主な成果物 |
|----------|------|------------|
| Phase 1 | 基盤構築 | イベントソーシング、AR、状態機械 |
| Phase 2 | Hive構造 | Hive/Colony階層、Colony状態機械 |
| Phase 3 | Queen Bee | Colony代表エージェント、Opinion集約 |
| Phase 4 | Beekeeper | 横断調整、Conferenceモード |
| Phase 5 | Worker Bee | 実タスク実行、ツール連携 |
| Phase 6 | 自律運用 | 自動並列実行、障害回復 |
| Phase 7 | 継続改善 | 回顧・提案・承認サイクル |

### 10.3 ゲート条件詳細

#### Phase 6 ゲート条件（自律運用への移行）

Phase 5 完了後、Phase 6 に進むための必須条件:

| ID | 条件 | 検証方法 |
|----|------|----------|
| G6-01 | Colony間衝突検出機能が実装済み | `CONFLICT_DETECTED` イベントが発行可能 |
| G6-02 | 衝突解決プロトコルが定義済み | `CONFLICT_RESOLVED` イベントとマージルール |
| G6-03 | 標準失敗理由の分類が完了 | `FailureReason` enum の使用 |
| G6-04 | タイムアウト検出が実装済み | `OPERATION_TIMEOUT` イベント発行 |
| G6-05 | Action Classが実装済み | `ActionClass`, `TrustLevel` による分類 |
| G6-06 | 確認要求マトリクスが定義済み | `requires_confirmation()` 関数 |
| G6-07 | Conference モードが動作 | `CONFERENCE_STARTED/ENDED` イベント |

#### Phase 7 ゲート条件（継続改善への移行）

Phase 6 完了後、Phase 7 に進むための必須条件:

| ID | 条件 | 検証方法 |
|----|------|----------|
| G7-01 | Decision Protocolが実装済み | `PROPOSAL_CREATED`, `DECISION_APPLIED` イベント |
| G7-02 | 決定の上書き履歴が追跡可能 | `DECISION_SUPERSEDED` イベント |
| G7-03 | ProjectContractが定義済み | 目標・制約・非目標・決定の構造化共有 |
| G7-04 | 因果リンクで決定を遡及可能 | `parents` フィールドによるリンク |
| G7-05 | 全ての失敗がイベント化 | `OPERATION_FAILED` + 理由コード |

### 10.4 現在のステータス（v5.1）

Phase 1.5（フィードバック対応）の完了状況:

| 要件 | ステータス | 実装 |
|------|----------|------|
| Decision Protocol イベント | ✅ 完了 | `events.py` |
| Conference イベント | ✅ 完了 | `events.py` |
| ProjectContract スキーマ | ✅ 完了 | `models/project_contract.py` |
| Action Class 定義 | ✅ 完了 | `models/action_class.py` |
| Conflict Detection イベント | ✅ 完了 | `events.py` |
| Failure/Timeout イベント | ✅ 完了 | `events.py` |

これにより、Phase 6/7 へのゲート条件を満たすための基盤が整いました。

---

## 11. 今後の拡張

### 11.1 主要な計画

- [ ] LLM Orchestrator: 自律的なタスク分解・実行
- [ ] Artifact管理: 成果物の保存と参照
- [ ] 因果リンクの自動設定（[Issue #001](issues/001-lineage-auto-parents.md)）
- [ ] イベント署名: 改ざん者の特定

### 11.2 VS Code拡張の拡充

- [ ] 因果グラフ可視化（Webview）
- [ ] リアルタイムイベントストリーム

### 11.3 スケーラビリティ

- [ ] エンティティ別チェーン（並列書き込み対応）
- [ ] イベントアーカイブ
- [ ] 分散ストレージ対応

---

## 参照

- [QUICKSTART.md](QUICKSTART.md) - 動作確認手順
- [AGENTS.md](../AGENTS.md) - AI開発ガイドライン
- [コンセプト_v4.md](%E3%82%B3%E3%83%B3%E3%82%BB%E3%83%97%E3%83%88_v4.md) - コンセプト（作業用仕様・最新版）
- [コンセプト_v3.md](%E3%82%B3%E3%83%B3%E3%82%BB%E3%83%97%E3%83%88_v3.md) - コンセプト（v3・ベースライン）
