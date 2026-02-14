# AGENTS.md - ColonyForge Development Guidelines

このファイルはAIエージェント（GitHub Copilot、Claude等）がColonyForgeプロジェクトで作業する際のガイドラインです。

## 核心的信念

> **信頼できる部品を、信頼できる組み合わせ方をして、信頼できるシステムを作る**

この信念がColonyForgeの開発哲学の根幹です。

## 開発原則

### 1. テスト駆動開発 (TDD)

- **テストを先に書く**: 実装前にテストを書き、失敗することを確認する
- **小さな単位でテスト**: 各関数・クラスが単一責任を持ち、独立してテスト可能であること
- **テストは仕様である**: テストコードがドキュメントとして機能する
- **ブランチカバレッジ100%**: 全ての分岐パスをテストする

### テストカバレッジの哲学

> **カバレッジを通すことが目的ではない。そのパスが通る前提や状況を明らかにし、挙動を明確にすることが目的である。**

各テストケースには以下を明記する：
- **前提条件 (Arrange)**: どのような状態・データが存在するか
- **操作 (Act)**: 何をしたときに
- **期待結果 (Assert)**: どうなるべきか

### AAAパターン (Arrange-Act-Assert)

テストは**AAAパターン**で構造化し、各セクションをコメントで明示する：

```python
def test_event_hash_excludes_hash_field():
    """hashフィールド自体はハッシュ計算から除外される

    hashフィールドを含むデータと含まないデータで同じハッシュが得られることを確認。
    これにより、イベントのハッシュ値をイベント自体に含めても循環参照を避けられる。
    """
    # Arrange: hashフィールドの有無が異なる2つのデータを用意
    data_without_hash = {"type": "test", "value": 1}
    data_with_hash = {"type": "test", "value": 1, "hash": "ignored"}

    # Act: 両方のハッシュを計算
    hash_without = compute_hash(data_without_hash)
    hash_with = compute_hash(data_with_hash)

    # Assert: hashフィールドの有無に関わらず同じハッシュになる
    assert hash_without == hash_with
```

### テストの可読性ガイドライン

1. **docstringで目的を説明**: テストが何を検証するのか、なぜ重要なのかを記述
2. **Arrange/Act/Assertをコメントで明示**: 各セクションの境界を明確に
3. **変数名は意図を表現**: `data1`, `data2`ではなく`data_without_hash`, `data_with_hash`
4. **1テスト1検証**: 1つのテストで1つの振る舞いのみを検証

### 2. 細かいコミット

- **1つの変更 = 1つのコミット**: 論理的に独立した変更ごとにコミット
- **コミットメッセージは明確に**: `feat:`, `fix:`, `test:`, `chore:`, `docs:`, `refactor:` のプレフィックスを使用
- **壊れた状態をコミットしない**: 各コミットでテストが通る状態を維持

### Git ワークフロー

開発系プロジェクトでは、Colony ベースの並列開発を安全に回すための Git 運用規約に従う。
詳細は **[docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md)** を参照。

#### ブランチモデル

| ブランチ | 用途 | 寿命 |
|---------|------|------|
| `master` | リリース専用（保護） | 永続 |
| `develop` | 統合トランク | 永続 |
| `feat/<hive>/<colony>/<ticket>-<slug>` | Colony 作業 | **短命**（1〜3日） |
| `fix/…`, `hotfix/…` | 障害対応 | 短命 |
| `exp/…` | 実験（使い捨て） | 任意 |

#### Worktree 運用

Colony 単位で `git worktree add` を使用し並列開発する。上限は 3 Worktree。

```bash
git worktree add ../wt-api -b feat/ec-site/api/123-login develop
```

#### Rebase / Merge 判定

- **個人ブランチ** → `develop`: rebase（線形履歴）
- **共有ブランチ** → `develop`: merge（履歴保護）
- `develop` → `master`: merge --no-ff（リリース境界明示）

#### PR ゲート（必須チェック）

- `guard-l1`: Lint / Unit / Schema
- `guard-l2`: 設計整合性
- `forager-regression`: 回帰テスト
- `sentinel-safety`: 安全性チェック

### 3. フォールバック禁止（Fail-Fast原則）

> **暗黙のフォールバックは問題の発見を遅らせ、意図しない動作を引き起こす。早期にエラーで検出できる方がはるかに安全である。**

- **フォールバック動作は原則として導入しない**: エラーが発生したら速やかに `raise` する
- **`except Exception` の広いキャッチは禁止**: キャッチする例外は具体的な型に限定する
- **エラーを握りつぶさない**: `except: pass` や `contextlib.suppress(Exception)` は使わない
- **エラー情報を文字列に変換して返さない**: `return {"error": str(e)}` ではなく例外を伝搬させる
- **ログだけ出して続行しない**: `logger.error(...)` の後に代替値を返すパターンは避ける

#### 許容されるフォールバック

以下のケースのみ、フォールバック動作を **コメントで理由を明記した上で** 許容する：

1. **安全側へのフォールバック**: 未知のツールを `DANGEROUS` 扱い、未知のエージェントを `UNTRUSTED` 扱いにする等
2. **例外のラッピング**: ドメイン固有例外への変換後に `raise`（`raise DomainError(...) from exc`）
3. **非同期キャンセル**: `asyncio.CancelledError` の標準的な抑制
4. **ユーザー向け境界**: FastAPI の HTTP エラーハンドラ等、外部インタフェースの最端レイヤーでのみ

#### 禁止パターンと代替

```python
# ❌ 禁止: 暗黙のフォールバック
try:
    plan = await planner.plan(goal)
except Exception:
    logger.error("LLMタスク分解に失敗")
    plan = TaskPlan(tasks=[PlannedTask(goal=goal)])  # 黙って1タスクに縮退

# ✅ 推奨: 早期エラー
plan = await planner.plan(goal)  # 例外はそのまま伝搬

# ❌ 禁止: エラーを文字列化して返す
try:
    result = execute_tool(args)
except Exception as e:
    return json.dumps({"error": str(e)})

# ✅ 推奨: 適切な例外を投げる
try:
    result = execute_tool(args)
except PermissionError as e:
    raise ToolExecutionError(f"権限不足: {e}") from e
# その他の例外はキャッチしない → 呼び出し元に伝搬

# ❌ 禁止: ログなしの握りつぶし
except Exception:
    pass

# ❌ 禁止: 広いキャッチで代替値
except Exception:
    return False
```

### 4. イミュータブル設計

- **イベントは不変**: 一度作成されたイベントは変更されない
- **状態は投影で再構築**: イベントから常に状態を再現可能
- **副作用の分離**: 純粋関数とI/Oを明確に分離

### 5. 信頼できる部品

- **Pydantic**: 型安全なデータモデル
- **ULID**: 時間順序付きユニークID
- **JCS (RFC 8785)**: 決定論的JSONシリアライズ
- **SHA-256**: 暗号学的ハッシュによるイベントチェーン

### 6. Pydanticによる厳格なスキーマ定義

- **厳格な型検証**: `strict=True`でランタイム型チェックを強制
- **OpenAPI仕様の自動生成**: FastAPIと連携してAPI仕様書を自動出力
- **バリデーションエラーは明確に**: エラーメッセージが人間に読みやすいこと
- **スキーマは単一責任**: 1つのモデルは1つの概念を表現

```python
from pydantic import BaseModel, Field, ConfigDict

class TaskCreatedEvent(BaseModel):
    """タスク作成イベント - OpenAPI仕様に出力される"""
    model_config = ConfigDict(strict=True, frozen=True)

    task_id: str = Field(..., description="タスクの一意識別子", examples=["task-001"])
    title: str = Field(..., min_length=1, max_length=200, description="タスクのタイトル")
```

### 7. ファイル分割の原則

- **1ファイル200行以下を目安**: 超える場合は分割を検討
- **1ファイル1責務**: 関連する機能をまとめつつ、肥大化を防ぐ
- **循環importを避ける**: 依存関係は一方向に
- **再利用可能な部品は独立**: 共通ユーティリティは専用モジュールに

```
# 良い例: 責務ごとに分割
core/events/
├── __init__.py      # 公開API
├── base.py          # BaseEvent
├── run.py           # Run関連イベント
├── task.py          # Task関連イベント
└── serialization.py # シリアライズ/デシリアライズ

# 悪い例: 1ファイルに全部
core/events.py  # 1000行超の巨大ファイル
```

## 開発環境

### devcontainer（推奨）

開発は**devcontainer**上で行う。これにより環境差異を排除し、再現可能なビルドを保証する。

```bash
# VS Codeでdevcontainerを開く
# コマンドパレット > "Dev Containers: Reopen in Container"
```

devcontainerには以下が含まれる：
- Python 3.12
- 必要な依存関係（`pip install -e ".[dev]"`済み）
- Ruff、pytest、mypy等の開発ツール
- VS Code拡張機能（Python、Pylance、Ruff等）

### ローカル開発（非推奨）

devcontainerを使用できない場合のみ：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## コードスタイル

- Python 3.11+
- 型ヒント必須
- Ruffでフォーマット・リント
- docstringは日本語可

## ディレクトリ構造

```
src/colonyforge/
├── core/           # コアロジック（イベント、状態機械、AR）
│   ├── events/     # イベントモデル（EventType enum等）
│   ├── models/     # ドメインモデル（ActionClass等）
│   ├── ar/         # Akashic Record（永続化）
│   ├── state/      # 状態機械
│   ├── honeycomb/  # 実行履歴・学習基盤（Episode, KPI）
│   ├── swarming/   # Swarming Protocol（適応的Colony編成）
│   ├── intervention/ # 介入・エスカレーション永続化
│   ├── github/     # GitHub Projection（PR/Issue同期）
│   ├── activity_bus.py  # Activity Bus
│   ├── config.py   # 設定管理
│   ├── lineage.py  # 因果リンク
│   ├── policy_gate.py # ポリシーゲート
│   └── rate_limiter.py # レートリミッター
├── api/            # FastAPI サーバー
├── mcp_server/     # MCP Server
├── beekeeper/      # Beekeeper（ユーザー窓口・Hive統括）
├── sentinel_hornet/ # Sentinel Hornet（監視・異常検出・強制停止）
├── queen_bee/      # Queen Bee（Colony統括）
├── worker_bee/     # Worker Bee（タスク実行）
├── guard_bee/      # Guard Bee（Evidence-first品質検証）
├── forager_bee/    # Forager Bee（探索的テスト・影響分析）
├── referee_bee/    # Referee Bee（N案採点・生存選抜）
├── scout_bee/      # Scout Bee（編成最適化）
├── waggle_dance/   # Waggle Dance（I/O構造化検証）
├── prompts/        # プロンプト集約パッケージ（英語化済み）
│   ├── agents.py         # エージェント別システムプロンプト
│   ├── task_decomposition.py # タスク分解プロンプト
│   ├── vlm.py            # VLMプロンプト
│   ├── loader.py         # PromptLoader, *Config
│   └── defaults/         # デフォルトプロンプトYAML
├── llm/            # LLM統合（AgentRunner, LLMクライアント）
│                   # ※ prompts.py / prompt_config.py は後方互換re-exportシム
├── agent_ui/       # Agent UI MCPサーバー
├── vlm/            # VLM（画像解析）
├── vlm_tester/     # VLM Tester（E2Eテスト支援）
├── requirement_analysis/ # 要求分析Colony（M6）
├── silence.py      # 沈黙検出
├── monitor/        # Hiveモニター（パッケージ化済み）
└── cli.py          # CLIツール

tests/              # テストコード（実装と1:1対応）
vscode-extension/   # VS Code拡張機能
```

## テスト実行

### ユニットテスト

```bash
# 全テスト（E2E除く）
pytest

# 特定のテスト
pytest tests/test_events.py -v

# カバレッジ付き
pytest --cov=colonyforge --cov-report=html
```

### E2Eビジュアルテスト

E2EテストはAgent UI + Playwright MCP + VLM(Ollama)を使用してUIをビジュアルに検証する。

#### 前提条件

devcontainerで以下のサービスが起動していること：

| サービス | ポート | 用途 |
|---------|-------|-----|
| `colonyforge-playwright-mcp` | 8931 | ブラウザ操作 |
| `colonyforge-dev-ollama` | 11434 | VLM画像解析 |
| `colonyforge-code-server` | 8080 | テスト対象VS Code |

```bash
# サービス起動確認
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

#### E2Eテスト実行

```bash
# 全E2Eテスト
PLAYWRIGHT_MCP_URL="http://colonyforge-playwright-mcp:8931" \
OLLAMA_BASE_URL="http://colonyforge-dev-ollama:11434" \
VLM_HEADLESS="true" \
pytest tests/e2e/test_colonyforge_visual.py -v -m e2e

# 特定のテストのみ
pytest tests/e2e/test_colonyforge_visual.py::TestColonyForgeExtensionVisual::test_can_capture_screen -v -m e2e
```

#### VS Codeタスクで実行

コマンドパレット（`Ctrl+Shift+P`）から：
- `Tasks: Run Test Task` → **E2E: ビジュアルテスト (pytest)**

#### E2Eテストの構造

```python
@pytest.mark.asyncio
async def test_vlm_recognizes_dashboard(self, agent_ui_server, demo_html_path):
    """VLMがダッシュボードを認識できることを確認"""
    # Arrange: ページに移動してキャプチャ
    await agent_ui_server._handle_navigate({"url": demo_html_path})
    await agent_ui_server._handle_capture_screen({})

    # Act: VLMでページを分析
    result = await agent_ui_server._handle_describe_page(
        {"focus": "What sections are visible?"}
    )

    # Assert: 期待するキーワードが含まれる
    analysis = get_text_from_result(result).lower()
    assert any(word in analysis for word in ["dashboard", "runs", "tasks"])
```

### VS Code拡張テスト

```bash
cd vscode-extension

# コンパイル（TypeScriptエラーチェック）
npm run compile

# Lint（ESLint）
npm run lint
```

## 作業フロー

### TDDサイクル（コーディング単位）

1. テストを書く（RED）
2. テストが失敗することを確認
3. 最小限の実装を書く（GREEN）
4. コミット
5. リファクタリング（REFACTOR）
6. コミット
7. 次のテストへ

### 機能開発フロー（全体）

```
1. ブランチ作成     develop から feat/ ブランチを切る
2. TDDサイクル      RED → GREEN → REFACTOR を繰り返す
3. 細かいコミット    論理単位ごとにコミット（壊れた状態をコミットしない）
4. rebase           develop の最新を取り込み（git rebase develop）
5. テスト全通過確認  pytest tests --ignore=tests/e2e -q
6. PR 作成          develop へ PR を出す
7. CI ゲート通過     guard-l1 / guard-l2 / forager-regression / sentinel-safety
8. マージ           rebase マージ（個人ブランチ）or merge（共有ブランチ）
9. ブランチ削除      マージ後にローカル・リモートブランチを削除
```

#### 手順例

```bash
# 1. develop から機能ブランチを作成
git checkout develop
git pull origin develop
git checkout -b feat/ec-site/api/42-user-auth

# 2-3. TDDサイクル → コミット（繰り返し）
pytest tests/test_auth.py -v        # RED: テスト失敗を確認
# ... 実装 ...
pytest tests/test_auth.py -v        # GREEN: テスト通過
git add -A && git commit -m "feat: ユーザー認証エンドポイント追加"

# 4. develop の最新を取り込み
git fetch origin
git rebase origin/develop

# 5. 全テスト通過確認
pytest tests --ignore=tests/e2e -q

# 6. プッシュ → PR
git push -u origin feat/ec-site/api/42-user-auth
gh pr create --base develop --title "feat: ユーザー認証" --body "..."

# 7-8. CI通過後にマージ
gh pr merge --rebase

# 9. ブランチ削除
git checkout develop && git pull
git branch -d feat/ec-site/api/42-user-auth
```

#### リリースフロー

```
develop → master: merge --no-ff（リリース境界を明示）
```

```bash
git checkout master
git merge --no-ff develop -m "release: v0.2.0"
git tag v0.2.0
git push origin master --tags
```

#### Hotfix フロー

```bash
git checkout -b hotfix/critical-bug master
# ... 修正 + テスト ...
git checkout master && git merge --no-ff hotfix/critical-bug
git checkout develop && git merge --no-ff hotfix/critical-bug
git branch -d hotfix/critical-bug
```

詳細は **[docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md)** を参照。
