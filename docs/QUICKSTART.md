# HiveForge クイックスタート

## 🚀 F5で即起動

devcontainer内で **F5キー** を押すとAPIサーバーが起動します。

| 構成名 | 説明 |
|--------|------|
| **HiveForge API Server** | REST API（デフォルト） |
| HiveForge MCP Server | MCP Server |
| Run Tests | pytest実行 |

**起動後:** http://localhost:8000/docs でSwagger UI

---

## 動作確認

1. **F5** → APIサーバー起動
2. ブラウザで http://localhost:8000/docs
3. Swagger UIで操作:
   - `POST /runs` → Run開始
   - `POST /runs/{id}/tasks` → Task作成  
   - `GET /runs/{id}` → 状態確認
   - `POST /runs/{id}/complete` → 完了

---

## テスト

```bash
pytest           # 全テスト（211件）
pytest -v        # 詳細表示
```

または **Run and Debug** → 「Run Tests」→ F5

---

<details>
<summary>📖 詳細手順（クリックで展開）</summary>

## 環境準備

### Devcontainer（推奨）
コマンドパレット → `Dev Containers: Reopen in Container`

### ローカル
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## API エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| GET | `/health` | ヘルスチェック |
| POST | `/runs` | Run開始 |
| GET | `/runs/{run_id}` | Run詳細 |
| POST | `/runs/{run_id}/complete` | Run完了 |
| POST | `/runs/{run_id}/emergency-stop` | 緊急停止 |
| POST | `/runs/{run_id}/tasks` | Task作成 |
| GET | `/runs/{run_id}/events` | イベント一覧 |
| GET | `/runs/{run_id}/events/{id}/lineage` | 因果リンク |

---

## MCP ツール

Copilot Chatで `@hiveforge` を使用（要: VS Code再読み込み）:

| ツール | 説明 |
|--------|------|
| `start_run` | Run開始 |
| `create_task` | Task作成 |
| `complete_task` | Task完了 |
| `emergency_stop` | 緊急停止 |
| `get_lineage` | 因果リンク取得 |

> **Note:** `@hiveforge`が出ない場合は `Developer: Reload Window` を実行

---

## curlでのテスト例

```bash
# Run開始
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "テスト"}'

# 緊急停止
curl -X POST http://localhost:8000/runs/{run_id}/emergency-stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "テスト停止"}'
```

---

## トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| Port 8000使用中 | `--port 8001` を指定 |
| command not found | `pip install -e ".[dev]"` |

</details>

---

詳細: [ARCHITECTURE.md](ARCHITECTURE.md)
