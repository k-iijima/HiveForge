# HiveForge 動作確認手順書

このドキュメントでは、HiveForgeの動作を確認する手順を説明します。

---

## 目次

1. [環境準備](#1-環境準備)
2. [APIサーバーの起動と確認](#2-apiサーバーの起動と確認)
3. [MCPサーバーの確認](#3-mcpサーバーの確認)
4. [VS Code拡張機能の確認](#4-vs-code拡張機能の確認)
5. [シナリオテスト](#5-シナリオテスト)
6. [テストの実行](#6-テストの実行)

---

## 1. 環境準備

### 1.1 Devcontainerで開発環境を起動

```bash
# VS Codeでプロジェクトを開く
code /workspace/HiveForge

# コマンドパレット → "Dev Containers: Reopen in Container"
```

### 1.2 ローカル環境（Devcontainerを使わない場合）

```bash
# 仮想環境を作成
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 依存パッケージをインストール
pip install -e ".[dev]"

# 環境変数を設定
cp .env.example .env
```

### 1.3 Vaultディレクトリの初期化

```bash
hiveforge init
```

**期待される出力:**
```
Vault initialized at ./Vault
```

---

## 2. APIサーバーの起動と確認

### 2.1 サーバー起動

```bash
hiveforge serve
```

**期待される出力:**
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 2.2 ヘルスチェック

別のターミナルで:

```bash
curl http://localhost:8000/health
```

**期待されるレスポンス:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "active_runs": 0
}
```

### 2.3 OpenAPI仕様の確認

ブラウザで http://localhost:8000/docs を開く

**利用可能なエンドポイント:**

| Method | Path | 説明 |
|--------|------|------|
| GET | `/health` | ヘルスチェック |
| POST | `/runs` | Run開始 |
| GET | `/runs` | Run一覧取得 |
| GET | `/runs/{run_id}` | Run詳細取得 |
| POST | `/runs/{run_id}/complete` | Run完了 |
| POST | `/runs/{run_id}/emergency-stop` | 緊急停止 |
| POST | `/runs/{run_id}/tasks` | Task作成 |
| GET | `/runs/{run_id}/tasks` | Task一覧取得 |
| POST | `/runs/{run_id}/tasks/{task_id}/complete` | Task完了 |
| POST | `/runs/{run_id}/tasks/{task_id}/fail` | Task失敗 |
| GET | `/runs/{run_id}/events` | イベント一覧取得 |
| GET | `/runs/{run_id}/events/{event_id}/lineage` | 因果リンク取得 |
| POST | `/runs/{run_id}/heartbeat` | ハートビート送信 |

### 2.4 基本的なワークフロー確認

#### Run開始

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "Hello Worldアプリを作成"}'
```

**期待されるレスポンス:**
```json
{
  "run_id": "01HZZ...",
  "goal": "Hello Worldアプリを作成",
  "state": "running",
  "started_at": "2026-01-31T12:00:00Z"
}
```

#### Task作成

```bash
curl -X POST http://localhost:8000/runs/{run_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "プロジェクト構造を作成", "description": "基本的なファイル構造を作成する"}'
```

#### イベント一覧取得

```bash
curl http://localhost:8000/runs/{run_id}/events
```

#### 因果リンク取得

```bash
curl "http://localhost:8000/runs/{run_id}/events/{event_id}/lineage?direction=both&max_depth=10"
```

**期待されるレスポンス:**
```json
{
  "event_id": "01HZZ...",
  "ancestors": ["01HZY...", "01HZX..."],
  "descendants": ["01J00...", "01J01..."],
  "truncated": false
}
```

#### 緊急停止

```bash
curl -X POST http://localhost:8000/runs/{run_id}/emergency-stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "テスト停止", "scope": "run"}'
```

---

## 3. MCPサーバーの確認

### 3.1 MCPサーバーの直接起動テスト

```bash
python -m hiveforge.mcp_server
```

**注意:** MCPサーバーはstdio経由で通信するため、通常はVS Codeから起動されます。

### 3.2 VS Code MCP設定

`.vscode/mcp.json` を作成:

```json
{
  "servers": {
    "hiveforge": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "hiveforge.mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "HIVEFORGE_VAULT_PATH": "${workspaceFolder}/Vault"
      }
    }
  }
}
```

### 3.3 利用可能なMCPツール

| ツール名 | 説明 | 必須パラメータ |
|----------|------|----------------|
| `start_run` | 新しいRunを開始 | `goal` |
| `get_run_status` | Run状態を取得 | - |
| `create_task` | Taskを作成 | `title` |
| `assign_task` | Taskを割り当て | `task_id` |
| `report_progress` | 進捗を報告 | `task_id`, `progress` |
| `complete_task` | Taskを完了 | `task_id` |
| `fail_task` | Taskを失敗 | `task_id`, `error` |
| `create_requirement` | 要件確認を作成 | `description` |
| `complete_run` | Runを完了 | - |
| `heartbeat` | ハートビート送信 | - |
| `emergency_stop` | 緊急停止 | `reason` |
| `get_lineage` | 因果リンクを取得 | `event_id` |

### 3.4 Copilot Chatでの使用例

Copilot Chatで以下のように対話できます:

```
User: @hiveforge 新しいRunを開始して、目標は「Webスクレイパーを作成」

User: @hiveforge 現在の状態を教えて

User: @hiveforge タスクを作成：「BeautifulSoupをインストール」

User: @hiveforge 緊急停止して、理由は「テスト終了」
```

---

## 4. VS Code拡張機能の確認

### 4.1 拡張機能のビルド

```bash
cd vscode-extension
npm install
npm run compile
```

### 4.2 拡張機能のデバッグ

1. VS Codeで `vscode-extension` フォルダを開く
2. F5キーで「Extension Development Host」を起動
3. 新しいVS Codeウィンドウで拡張機能が有効になる

### 4.3 利用可能な機能

- **ダッシュボード表示**: コマンドパレット → "HiveForge: Dashboard"
- **イベントログ表示**: サイドバーの HiveForge ビュー
- **ステータスバー**: 現在のRun状態を表示

---

## 5. シナリオテスト

### シナリオ1: 基本的なRun→Task→完了フロー

```bash
# 1. Run開始
RUN_ID=$(curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "テストRun"}' | jq -r '.run_id')

echo "Run ID: $RUN_ID"

# 2. Task作成
TASK_ID=$(curl -s -X POST http://localhost:8000/runs/$RUN_ID/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "テストTask"}' | jq -r '.task_id')

echo "Task ID: $TASK_ID"

# 3. Task完了
curl -X POST http://localhost:8000/runs/$RUN_ID/tasks/$TASK_ID/complete \
  -H "Content-Type: application/json" \
  -d '{"result": {"message": "成功"}}'

# 4. Run完了
curl -X POST http://localhost:8000/runs/$RUN_ID/complete

# 5. イベントログ確認
curl http://localhost:8000/runs/$RUN_ID/events | jq
```

### シナリオ2: 緊急停止フロー

```bash
# 1. Run開始
RUN_ID=$(curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "緊急停止テスト"}' | jq -r '.run_id')

# 2. 緊急停止
curl -X POST http://localhost:8000/runs/$RUN_ID/emergency-stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "テスト停止", "scope": "run"}'

# 3. 状態確認（abortedになっていること）
curl http://localhost:8000/runs/$RUN_ID | jq '.state'
```

### シナリオ3: 因果リンクの確認

```bash
# 1. Run開始
RUN_ID=$(curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "因果リンクテスト"}' | jq -r '.run_id')

# 2. イベントを取得
EVENTS=$(curl -s http://localhost:8000/runs/$RUN_ID/events)
FIRST_EVENT_ID=$(echo $EVENTS | jq -r '.[0].id')

# 3. 因果リンクを取得
curl "http://localhost:8000/runs/$RUN_ID/events/$FIRST_EVENT_ID/lineage?direction=both"
```

---

## 6. テストの実行

### 6.1 全テストを実行

```bash
pytest tests/ -v
```

**期待される出力:**
```
============================= 211 passed in X.XXs ==============================
```

### 6.2 カバレッジ付きテスト

```bash
pytest tests/ --cov=hiveforge --cov-report=term-missing
```

**期待される出力:**
```
TOTAL                                   1081      0    248      0   100%
Required test coverage of 100.0% reached. Total coverage: 100.00%
```

### 6.3 特定のテストファイルを実行

```bash
# APIテスト
pytest tests/test_api.py -v

# MCPサーバーテスト
pytest tests/test_mcp_server.py -v

# イベントテスト
pytest tests/test_events.py -v
```

### 6.4 特定のテストクラス/関数を実行

```bash
# 緊急停止のテストのみ
pytest tests/test_api.py::TestRunsEndpoints::test_emergency_stop -v

# 因果リンクのテストのみ
pytest tests/test_api.py::TestLineageWithParents -v
```

---

## トラブルシューティング

### よくある問題

| 問題 | 解決策 |
|------|--------|
| `hiveforge: command not found` | `pip install -e ".[dev]"` を再実行 |
| `Port 8000 already in use` | 別ポートを指定: `hiveforge serve --port 8001` |
| `Vault directory not found` | `hiveforge init` を実行 |
| MCP接続エラー | VS Codeを再起動し、MCP設定を確認 |

### ログの確認

```bash
# Vaultディレクトリの内容
ls -la Vault/

# イベントログファイル
cat Vault/{run_id}/events.jsonl
```

---

## 次のステップ

- [ARCHITECTURE.md](ARCHITECTURE.md) - システム設計の詳細
- [AGENTS.md](../AGENTS.md) - AI開発ガイドライン
- [コンセプト_v3.md](../コンセプト_v3.md) - 完全な設計仕様
