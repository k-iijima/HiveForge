# REST APIリファレンス

ColonyForgeはFastAPIベースのREST APIを提供します。サーバー起動後、`http://localhost:8000/docs`（Swagger UI）で完全な対話型ドキュメントを利用できます。

## ベースURL

```
http://localhost:8000
```

## エンドポイント一覧

### システム

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/health` | ヘルスチェック |
| GET | `/openapi.json` | OpenAPI仕様 |

### Run

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/runs` | 新しいRunを開始 |
| GET | `/runs` | Run一覧 |
| GET | `/runs/{run_id}` | Run詳細 |
| POST | `/runs/{run_id}/complete` | Runを完了 |
| POST | `/runs/{run_id}/emergency-stop` | 緊急停止 |

### Task

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/runs/{run_id}/tasks` | Taskを作成 |
| GET | `/runs/{run_id}/tasks` | Run内のTask一覧 |
| POST | `/runs/{run_id}/tasks/{task_id}/assign` | Taskを割り当て |
| POST | `/runs/{run_id}/tasks/{task_id}/complete` | Taskを完了 |
| POST | `/runs/{run_id}/tasks/{task_id}/fail` | Taskを失敗 |
| POST | `/runs/{run_id}/tasks/{task_id}/progress` | Task進捗を報告 |

### イベント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/runs/{run_id}/events` | Run内のイベント一覧 |
| GET | `/runs/{run_id}/events/{event_id}/lineage` | イベントの因果リンク |

### Requirement（承認）

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/runs/{run_id}/requirements` | 承認要請を作成 |
| POST | `/runs/{run_id}/requirements/{req_id}/approve` | 承認 |
| POST | `/runs/{run_id}/requirements/{req_id}/reject` | 却下 |

### Hive

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/hives` | Hiveを作成 |
| GET | `/hives` | Hive一覧 |
| GET | `/hives/{hive_id}` | Hive詳細 |
| POST | `/hives/{hive_id}/close` | Hiveを終了 |

### Colony

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/hives/{hive_id}/colonies` | Colonyを作成 |
| GET | `/hives/{hive_id}/colonies` | Colony一覧 |
| POST | `/colonies/{colony_id}/start` | Colonyを開始 |
| POST | `/colonies/{colony_id}/complete` | Colonyを完了 |

### Conference

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/conferences` | 会議を開始 |
| GET | `/conferences` | 会議一覧 |
| GET | `/conferences/{conf_id}` | 会議詳細 |
| POST | `/conferences/{conf_id}/end` | 会議を終了 |

### Guard Bee（品質検証）

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/guard-bee/verify` | 証拠付き検証を提出 |
| GET | `/guard-bee/reports/{run_id}` | 検証レポートを取得 |

### KPI / Honeycomb

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/kpi/evaluation` | KPI評価サマリーを取得 |
| GET | `/kpi/episodes` | 記録済みエピソード一覧 |

### 介入

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/interventions/user-intervene` | ユーザー直接介入 |
| POST | `/interventions/queen-escalate` | Queen Beeエスカレーション |
| POST | `/interventions/beekeeper-feedback` | フィードバックを記録 |
| GET | `/interventions/escalations` | エスカレーション一覧 |
| GET | `/interventions/escalations/{esc_id}` | エスカレーション詳細 |

### Beekeeper

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/beekeeper/message` | Beekeeperにメッセージ送信 |
| GET | `/beekeeper/status` | Beekeeperステータス |

### アクティビティフィード

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/activities` | アクティビティフィード |

## 自動生成モジュールリファレンス

### イベント

::: colonyforge.core.events.base
    options:
      show_root_heading: true
      members_order: source

::: colonyforge.core.events.types
    options:
      show_root_heading: true
      members_order: source

### Akashic Record

::: colonyforge.core.ar.storage
    options:
      show_root_heading: true
      members_order: source

### Honeycomb

::: colonyforge.core.honeycomb.kpi
    options:
      show_root_heading: true
      members_order: source

::: colonyforge.core.honeycomb.models
    options:
      show_root_heading: true
      members_order: source

### ドメインモデル

::: colonyforge.core.models.action_class
    options:
      show_root_heading: true
      members_order: source
