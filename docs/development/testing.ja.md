# テスト

## テスト戦略

ColonyForgeは全コアモジュールで**ブランチカバレッジ100%**を目標とします。

> **カバレッジを通すことが目的ではない。そのパスが通る前提や状況を明らかにし、挙動を明確にすることが目的である。**

## テスト実行

### ユニットテスト

```bash
# 全テスト（E2E除く）
pytest

# 特定のテストファイル
pytest tests/test_events.py -v

# カバレッジ付き
pytest --cov=colonyforge --cov-report=html
```

### E2Eビジュアルテスト

E2EテストはAgent UI + Playwright MCP + VLM（Ollama）を使用してUIをビジュアルに検証します。

#### 前提条件

devcontainerで以下のサービスが起動していること：

| サービス | ポート | 用途 |
|---------|-------|-----|
| `colonyforge-playwright-mcp` | 8931 | ブラウザ操作 |
| `colonyforge-dev-ollama` | 11434 | VLM画像解析 |
| `colonyforge-code-server` | 8080 | テスト対象VS Code |

#### E2Eテスト実行

```bash
PLAYWRIGHT_MCP_URL="http://colonyforge-playwright-mcp:8931" \
OLLAMA_BASE_URL="http://colonyforge-dev-ollama:11434" \
VLM_HEADLESS="true" \
pytest tests/e2e/test_colonyforge_visual.py -v -m e2e
```

VS Codeタスク経由：コマンドパレット → `Tasks: Run Test Task` → **E2E: ビジュアルテスト (pytest)**

### VS Code拡張テスト

```bash
cd vscode-extension
npm run compile  # TypeScriptエラーチェック
npm run lint     # ESLint
```

## テスト統計

| カテゴリ | 件数 |
|---------|------|
| ユニットテスト | ~2,370+ |
| E2Eテスト | 51 |
| カバレッジ最低値 | 96% |

## テスト構造

### AAAパターン (Arrange-Act-Assert)

```python
def test_run_completion_requires_all_tasks_done():
    """Taskが残っている状態ではRunを完了できない。

    状態機械がRun完了前にタスク完了を強制することを検証。
    """
    # Arrange: 未完了タスクを持つRunを作成
    run = create_test_run()
    create_test_task(run.run_id, status="pending")

    # Act & Assert: 完了を試みるとエラーが発生するべき
    with pytest.raises(InvalidStateTransitionError):
        complete_run(run.run_id)
```

### テストカテゴリ

| マーカー | 説明 |
|---------|------|
| （デフォルト） | ユニットテスト — `pytest` で実行 |
| `@pytest.mark.e2e` | E2Eテスト（ブラウザ/コンテナ必要） |
| `@pytest.mark.benchmark` | パフォーマンスベンチマーク |

### E2Eテストクラス

| クラス | 件数 | テスト対象 |
|-------|------|----------|
| `TestHiveMonitorRealRendering` | 19 | アクセシビリティスナップショットDOM検証 |
| `TestHiveMonitorValueConsistency` | 16 | API→表示値の完全一致 |
| `TestHiveMonitorVLMVisualEval` | 8 | VLMレイアウト/色/テーマ認識 |
| `TestHiveMonitorVLMOCR` | 10 | VLMテキスト可読性・正確な値のOCR |
