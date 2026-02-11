# コンセプト

## 階層モデル

ColonyForgeは4階層構造で作業を組織化します：

```mermaid
graph TD
    H[Hive - プロジェクト] --> C1[Colony - UI/UX]
    H --> C2[Colony - API]
    H --> C3[Colony - インフラ]
    C1 --> R1[Run 1]
    C1 --> R2[Run 2]
    C2 --> R3[Run 3]
    R1 --> T1[Task 1]
    R1 --> T2[Task 2]
    R3 --> T3[Task 3]
```

### Hive

**Hive**は最上位の組織単位で、プロジェクトやイニシアチブを表します。

- 複数のColonyを含む
- Beekeeperエージェントが管理
- 状態: `active` → `closed`

### Colony

**Colony**はHive内の専門作業グループで、特定のドメイン（UI、API、インフラなど）に特化します。

- 複数のRunを含む
- Queen Beeエージェントが管理
- 状態: `pending` → `active` → `completed` / `failed`

### Run

**Run**は1回の実行パスを表します。Run内の全状態変更はイベントとして記録されます。

- TaskとRequirementを含む
- 状態: `running` → `completed` / `stopped` / `failed` / `timed_out`

### Task

**Task**はRun内の原子的な作業単位です。

- 状態: `pending` → `in_progress` → `completed` / `failed` / `cancelled`
- 完了時に結果を記録

### Requirement（承認要請）

**Requirement**は続行前にユーザーの承認が必要な確認要請を表します。

- 状態: `pending` → `approved` / `rejected` / `cancelled`
- ActionClassとTrustLevelにより制御

## イベントソーシング

ColonyForgeの全状態変更は**不変イベント**としてAkashic Record (AR) に記録されます。

```mermaid
sequenceDiagram
    participant User as ユーザー
    participant API
    participant AR as Akashic Record

    User->>API: POST /runs
    API->>AR: RunStartedイベントを追記
    API-->>User: Run ID

    User->>API: POST /runs/{id}/tasks
    API->>AR: TaskCreatedイベントを追記
    API-->>User: Task ID

    User->>API: POST /tasks/{id}/complete
    API->>AR: TaskCompletedイベントを追記
    API-->>User: OK
```

### イベントの構成要素

全てのイベントは以下を含みます：

| フィールド | 説明 |
|-----------|------|
| `event_id` | ユニークID（ULID — 時間順序付き） |
| `run_id` | 所属するRun |
| `event_type` | 型列挙（例: `RUN_STARTED`, `TASK_COMPLETED`） |
| `timestamp` | ISO 8601タイムスタンプ |
| `hash` | 正準JSON (JCS) のSHA-256ハッシュ |
| `parent_hash` | 前イベントのハッシュ — チェーンを形成 |

### 因果追跡（Lineage）

イベントは因果的にリンクでき、任意の成果物が「なぜ」作られたかを遡及できます。

```
TaskCompleted → リンク → TaskCreated → リンク → RunStarted
```

`GET /runs/{run_id}/events/{event_id}/lineage` で因果グラフを探索できます。

## 状態機械

各エンティティは厳密な状態機械に従います。無効な遷移は即座にエラーを発生させます（fail-fast）。

### Runの状態

```mermaid
stateDiagram-v2
    [*] --> running: 開始
    running --> completed: 完了（全タスク完了）
    running --> stopped: 緊急停止
    running --> failed: 失敗
    running --> timed_out: タイムアウト
```

### Taskの状態

```mermaid
stateDiagram-v2
    [*] --> pending: 作成
    pending --> in_progress: 割当
    in_progress --> completed: 完了
    in_progress --> failed: 失敗
    pending --> cancelled: キャンセル
    in_progress --> cancelled: キャンセル
```

## ActionClassと信頼レベル

操作はリスクレベルで分類されます：

| ActionClass | 例 | 承認 |
|-------------|-----|------|
| `SAFE` | ファイル読取、検索 | 自動承認 |
| `NORMAL` | ファイル作成、テスト実行 | 信頼レベルに依存 |
| `DANGEROUS` | ファイル削除、コマンド実行 | 承認必要 |
| `CRITICAL` | デプロイ、データ移行 | 常に承認必要 |

信頼レベル（`UNTRUSTED`、`BASIC`、`TRUSTED`、`ADMIN`）が承認閾値を決定します。

## Honeycomb（学習基盤）

HoneycombシステムはColonyのパフォーマンススナップショットである実行**エピソード**を記録し、KPIを計算します：

| KPI | 説明 |
|-----|------|
| Correctness | 失敗なしで完了したタスクの割合 |
| Guard Pass Rate | 品質検証合格率 |
| Repeatability | 複数実行間の一貫性 |
| Avg Cycle Time | 平均タスク完了時間 |
| Collaboration Score | Colony間連携の品質 |

これらのKPIは時系列のトレンド追跡により改善サイクル（PDCA）を可能にします。
