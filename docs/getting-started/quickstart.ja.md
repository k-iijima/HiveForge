# クイックスタート

HiveForgeを起動し、最初のワークフローを5分で完了しましょう。

## 1. APIサーバーの起動

VS Codeで**F5**キーを押す（devcontainer内）、または：

```bash
hiveforge server
```

Swagger UIを開く：[http://localhost:8000/docs](http://localhost:8000/docs)

## 2. Hiveの作成

Hiveはプロジェクトを表す最上位の組織単位です。

```bash
curl -X POST http://localhost:8000/hives \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project", "description": "最初のHiveForgeプロジェクト"}'
```

## 3. Colonyの作成

ColonyはHive内の専門作業グループです。

```bash
curl -X POST http://localhost:8000/hives/{hive_id}/colonies \
  -H "Content-Type: application/json" \
  -d '{"name": "Feature A", "goal": "機能Aを実装"}'

# Colonyを開始
curl -X POST http://localhost:8000/colonies/{colony_id}/start
```

## 4. Runの開始

Runは1回の作業実行パスを表します。

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "ログイン機能を実装"}'
```

## 5. Taskの作成と完了

```bash
# Taskを作成
curl -X POST http://localhost:8000/runs/{run_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "ログインフォーム作成", "description": "HTML/CSSログインフォーム"}'

# Taskを完了
curl -X POST http://localhost:8000/runs/{run_id}/tasks/{task_id}/complete \
  -H "Content-Type: application/json" \
  -d '{"result": "ログインフォーム作成完了"}'
```

## 6. Runの完了

```bash
curl -X POST http://localhost:8000/runs/{run_id}/complete
```

!!! tip "ヒント"
    未完了タスクがある場合は `{"force": true}` で強制完了できます（残りのタスク・確認要請を自動キャンセル）。

## 7. VS Codeで表示

HiveForge拡張機能をインストールすると以下が表示されます：

- **Hive Monitor** — KPIゲージ付きWebviewダッシュボード
- **イベントログ** — 全イベントのTreeView表示
- **ステータスバー** — 現在のRun状態

## MCP経由の操作（GitHub Copilot Chat）

`.vscode/mcp.json` を設定：

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

Copilot Chatで `@hiveforge` を入力してHiveForgeを直接操作できます。

## 次のステップ

- [コンセプト](../guide/concepts.md) — Hive/Colony/Run/Taskモデルを理解する
- [CLIリファレンス](../guide/cli.md) — 全CLIコマンド
- [エージェント](../guide/agents.md) — 各エージェントの役割を学ぶ
