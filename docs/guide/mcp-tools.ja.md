# MCPツール

HiveForgeは[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)を通じてGitHub Copilot Chatで使用できるツールを公開しています。

## セットアップ

ワークスペースに `.vscode/mcp.json` を作成：

```json
{
  "servers": {
    "hiveforge": {
      "command": "hiveforge",
      "args": ["mcp"],
      "env": {}
    }
  }
}
```

VS Codeを再読み込み（コマンドパレット → **Developer: Reload Window**）。

Copilot Chatで `@hiveforge` を入力してツールにアクセスします。

## ツールリファレンス

### Hive / Colony管理

| ツール | 説明 |
|--------|------|
| `create_hive` | 新しいHive（プロジェクト単位）を作成 |
| `list_hives` | Hive一覧を取得 |
| `get_hive` | Hiveの詳細情報とステータスを取得 |
| `close_hive` | Hiveを終了 |
| `create_colony` | Hive内にColonyを作成 |
| `list_colonies` | Hive内のColony一覧を取得 |
| `start_colony` | Colonyを開始 |
| `complete_colony` | Colonyを完了 |

### Run / Task操作

| ツール | 説明 |
|--------|------|
| `start_run` | 目標を指定して新しいRunを開始 |
| `get_run_status` | Runの進捗、タスク、次のアクションを取得 |
| `create_task` | Run内にTaskを作成 |
| `assign_task` | Taskを割り当てて作業を開始 |
| `report_progress` | Taskの進捗を報告（0–100%） |
| `complete_task` | Taskを完了として結果を記録 |
| `fail_task` | Taskを失敗としてエラー内容を記録 |
| `complete_run` | Runを完了 |
| `heartbeat` | 沈黙検出を防ぐためハートビートを送信 |
| `emergency_stop` | Runを緊急停止 |

### Decision / 因果追跡

| ツール | 説明 |
|--------|------|
| `record_decision` | Decisionイベントを記録（Dキー、理由、選択肢） |
| `get_lineage` | 任意のイベントの因果リンクを取得 |

### Conference

| ツール | 説明 |
|--------|------|
| `start_conference` | 複数Colony参加の会議を開始 |
| `end_conference` | サマリーと決定事項で会議を終了 |
| `list_conferences` | 会議一覧を取得 |
| `get_conference` | 会議の詳細情報を取得 |

### 品質検証

| ツール | 説明 |
|--------|------|
| `verify_colony` | Guard BeeのL1/L2検証を証拠付きで実行 |
| `get_guard_report` | Run配下のGuard Bee検証レポートを取得 |

### 承認 / 確認要請

| ツール | 説明 |
|--------|------|
| `create_requirement` | ユーザー承認が必要な要件を作成 |
| `approve` | 承認待ちの操作を承認 |
| `reject` | 承認待ちの操作を拒否 |

### 介入 / エスカレーション

| ツール | 説明 |
|--------|------|
| `user_intervene` | ユーザー直接介入（Beekeeperをバイパス） |
| `queen_escalate` | Queen Beeからユーザーへのエスカレーション |
| `beekeeper_feedback` | 介入後のBeekeeperフィードバックを記録 |
| `list_escalations` | エスカレーション一覧を取得 |
| `get_escalation` | エスカレーションの詳細情報を取得 |

### Beekeeper

| ツール | 説明 |
|--------|------|
| `send_message` | Beekeeperにメッセージを送信 |
| `get_beekeeper_status` | Beekeeper経由でHive/Colony状態を取得 |

### GitHub連携

| ツール | 説明 |
|--------|------|
| `sync_run_to_github` | RunのイベントをGitHub Issues/Comments/Labelsに同期（冪等） |
| `get_github_sync_status` | GitHub Projectionの同期状態を取得 |
