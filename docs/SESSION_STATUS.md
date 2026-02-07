# セッションステータス - 2026/02/07

## 概要

HiveForgeプロジェクトのプロンプトYAML統合が完了。各エージェント（Beekeeper, Queen Bee, Worker Bee）が
YAML設定ファイルからカスタムプロンプトを読み込めるようになった。

## 完了した作業

### 今回のセッション (2026/02/07)

1. **devcontainer改善のコミット＆push**
   - Docker Desktop対応（GPU専用 → 汎用化）
   - Playwright MCP ServerをローカルDockerfileでビルド
   - 10コミット分をorigin/masterにpush

2. **プロンプトYAML統合**（全エージェント）
   - `AgentRunner`に`vault_path`, `hive_id`, `colony_id`, `worker_name`パラメータ追加
   - `_resolve_system_prompt()`メソッドでYAML → デフォルトのフォールバック
   - Beekeeper: `vault_path`を渡す
   - Queen Bee: `vault_path` + `colony_id`を渡す
   - Worker Bee: `vault_path` + `worker_id`を渡す
   - テスト10件追加（7件AgentRunner + 3件サーバー）

3. **hiveforge.config.yaml整理**
   - agentsセクションにプロンプトYAML読み込み優先順位を記載
   - ファイル命名規則と配置例を追加
   - ガバナンス設定とプロンプト設定の役割分担を明確化

### 前回セッション (〜2026/02/01)

```
User → Beekeeper → Queen Bee → Worker Bee
          ↓            ↓           ↓
      対話窓口     タスク分解    タスク実行
```

- **Beekeeper MCP Server** (`src/hiveforge/beekeeper/server.py`)
  - ユーザーとの対話窓口
  - `delegate_to_queen` でQueen Beeに作業を委譲
  - テスト: 22件

- **Queen Bee MCP Server** (`src/hiveforge/queen_bee/server.py`)
  - Colonyを統括、タスク分解
  - Worker Beeの`execute_task_with_llm`を呼び出し
  - テスト: 20件

- **Worker Bee MCP Server** (`src/hiveforge/mcp_server/server.py`)
  - 具体的なタスクを実行
  - LLM統合済み

### 2. CLIコマンド

```bash
hiveforge chat "メッセージ"  # Beekeeperと対話
```

### 3. プロンプトYAMLカスタマイズ（今回実装）

```
src/hiveforge/llm/
├── prompt_config.py          # スキーマ + PromptLoader
├── prompts.py                # 取得関数
└── default_prompts/          # パッケージ内デフォルト
    ├── beekeeper.yml
    ├── queen_bee.yml
    └── default_worker_bee.yml

Vault/hives/                  # カスタマイズ配置先
├── {hive_id}/
│   ├── beekeeper.yml
│   └── colonies/
│       └── {colony_id}/
│           ├── queen_bee.yml
│           └── {name}_worker_bee.yml
```

**読み込み優先順位:**
1. Vault/hives/{hive_id}/colonies/{colony_id}/ - Colony固有
2. Vault/hives/{hive_id}/ - Hive全体
3. src/hiveforge/llm/default_prompts/ - パッケージ内
4. ハードコードデフォルト

## Git状態

```
ブランチ: master（origin/masterと同期済み）
```

## 動作確認済みコマンド

```bash
# エージェント間通信の動作確認（成功）
hiveforge chat "カレントディレクトリのファイル一覧を表示して"
# → Beekeeper → Queen Bee → Worker Bee → list_directory → 結果表示
```

## プロンプト読み込みフロー（完成版）

```
AgentRunner.run()
  → _resolve_system_prompt()
    → vault_pathあり? → get_prompt_from_config()
      → PromptLoader._find_config_file()
        → 1. Vault/hives/{hive_id}/colonies/{colony_id}/
        → 2. Vault/hives/{hive_id}/
        → 3. src/hiveforge/llm/default_prompts/
        → 4. ハードコードフォールバック
    → vault_pathなし? → get_system_prompt() (後方互換)
```

## 次に検討すべき作業

1. **hive_idの引き回し**
   - Beekeeper/Queen Beeが実行時にhive_idを受け取り、AgentRunnerに渡す
   - 現状はデフォルト"0"を使用

2. **プロンプトYAMLの実運用テスト**
   - 実際のVaultにカスタムプロンプトを配置して動作確認
   - `hiveforge chat`コマンドでの統合テスト

3. **VS Code拡張連携**
   - プロンプトYAML編集UIの提供
   - Hive/Colony/Worker設定のツリービュー
   - 重複する設定の統合

3. **git push**
   - 8コミットがローカルのみ

4. **その他の機能拡張**
   - 名前付きWorker Bee（coder, reviewer等）の実装
   - 複数Colony管理

## 環境情報

- Python 3.12
- devcontainer環境
- 依存関係: pyproject.toml参照

## 再開時の手順

1. devcontainerを開く
2. テスト実行で環境確認:
   ```bash
   pytest tests --ignore=tests/e2e -q
   ```
3. 動作確認:
   ```bash
   hiveforge chat "テスト"
   ```

## 関連ファイル

| ファイル | 説明 |
|---------|------|
| src/hiveforge/beekeeper/server.py | Beekeeper MCPサーバー |
| src/hiveforge/queen_bee/server.py | Queen Bee MCPサーバー |
| src/hiveforge/mcp_server/server.py | Worker Bee MCPサーバー |
| src/hiveforge/llm/prompt_config.py | プロンプトYAMLスキーマ |
| src/hiveforge/llm/prompts.py | プロンプト取得関数 |
| src/hiveforge/cli.py | CLIコマンド（chat含む） |
| hiveforge.config.yaml | 全体設定 |
| tests/test_prompt_config.py | プロンプト設定テスト（29件） |
| tests/test_beekeeper_server.py | Beekeeperテスト（22件） |
| tests/test_queen_bee_server.py | Queen Beeテスト（20件） |
