# HiveForge 開発計画 v2

> **策定日**: 2026-02-08
> **前版**: [DEVELOPMENT_PLAN_v1.md](archive/DEVELOPMENT_PLAN_v1.md) — 2026-02-07策定
> **トリガー**: v1.5コンセプト（Swarming Protocol, Guard Bee, Honeycomb等）の導入に伴い計画を再編
> **コンセプト**: [コンセプト_v6.md](コンセプト_v6.md)

---

## 1. 現状の事実認定（2026-02-08 更新）

### 1.1 計測済みメトリクス

| 指標 | 実測値 | 備考 |
|------|--------|------|
| **ユニットテスト** | `pytest` で確認 | 固定値は記載しない（CIで自動取得） |
| **カバレッジ** | `pytest --cov` で確認 | 同上 |
| **Lint (Ruff)** | ✅ All passed | — |
| **EventType数** | 95 | `core/events/types.py` |

> テスト件数・カバレッジは**計測値のみを正とし**、ドキュメントに固定値を書かない。

### 1.2 コンポーネント別の実装実態

| コンポーネント | ステータス | 詳細 | 既知の制約 |
|---------------|-----------|------|------------|
| **Hive Core** (イベント, AR, 状態機械) | ✅ 完了 | 95 EventType, 5状態機械, ハッシュ連鎖 | — |
| **Hive/Colony AR永続化** | ✅ M1-1完了 | HiveStore + HiveAggregate, JSONL永続化 | — |
| **API Server** (FastAPI REST) | ✅ 完了 | Hive/Colony CRUD が AR永続化と接続済み | 認証ミドルウェア実装済 (`auth.enabled: false` がデフォルト) |
| **MCP Server** (Copilot連携) | ✅ 完了 | 全ツール実装・テスト済 | — |
| **CLI** | ✅ 完了 | `hiveforge chat` 等 | mypy strict未対応 (M1-3) |
| **Beekeeper server** | ✅ M2-2完了 | 全ハンドラ実装済 | — |
| **Beekeeper handler** | ✅ 完了 | — | — |
| **Queen Bee** | ✅ M4-1/M4-2完了 | LLMタスク分解・並列実行・ゲート統合実装済 | TaskPlanner + ColonyOrchestrator + ExecutionPipeline |
| **Worker Bee** | ✅ 完了 | ツール実行, リトライ, Trust | — |
| **Sentinel Hornet** | ✅ M3-6完了 | 7検出パターン + KPI劣化検出 + ロールバック/隔離 | — |
| **VS Code拡張** (コマンド) | ✅ M2-1完了 | API接続コード作成済、TSコンパイル+Lint確認済 | — |
| **VS Code拡張** (TreeView) | ✅ 完了 | Activity Hierarchy API連動 | — |
| **VS Code拡張** (Hive Monitor) | ✅ 完了 | リアルタイムWebview | — |
| **Agent UI / VLM / VLM Tester** | ✅ 完了 | — | VLM画像入力のbase64判定は仮定ベース |
| **Swarming Protocol Engine** | ✅ M3-2完了 | 3軸特徴量、4テンプレート、Beekeeper統合、Config対応 | ルールベース選択、将来Honeycombデータ駆動に移行予定 |
| **Guard Bee** | ✅ M3-3完了 | Evidence-first品質検証、2層検証(L1/L2)、5組込ルール | — |
| **Honeycomb** | ✅ M3-1完了 | Episodeモデル、JSONL永続化、KPI算出 | — |
| **Scout Bee** | ✅ M3-8完了 | 類似エピソード検索、テンプレート成功率分析、最適化提案 | 特徴量レンジ1〜5を固定仮定、コールドスタート時は`balanced`固定 |
| **Forager Bee** | ✅ M3-4完了 | 変更影響グラフ、シナリオ生成、探索実行、違和感検知 | — |
| **Referee Bee** | ✅ M3-5完了 | 5次元スコアリング、Differential Testing、トーナメント選拔 | — |
| **Waggle Dance** | ✅ M3-7完了 | Pydanticスキーマ検証、バリデーションミドルウェア、ARイベント記録 | — |
| **KPI Calculator** | ✅ M3-1完了 | HoneycombのKPICalculatorとして実装済 | — |
| **LLM Orchestrator** | ✅ M4-2完了 | ColonyOrchestrator（層別並列実行）+ ColonyResult（結果集約）+ ExecutionPipeline（ゲート統合） | — |
| **介入・エスカレーション** | ✅ 完了 | API/MCPハンドラ実装済、InterventionStore JSONL永続化 | — |
| **GitHub Projection** | ✅ 完了 | AR→GitHub Issue片方向同期、MCPハンドラ’実装済 | — |

---

## 2. マイルストーン体系

### 2.1 全体像

```
M1 (基盤固め)  → M2 (接続)    → M3 (適応的協調) → M4 (自律)    → M5 (運用)
 ■■■■■■■■■■     ■■■■■■■■■■     ■■■■■■■■■■         ■■■■■■■■■■     ░░░░░░░░░░
 完了              完了             完了                完了              プロダクション
```

### 2.2 完了マイルストーン

<details>
<summary>M1: 基盤固め ✅ 完了</summary>

#### M1-1: Hive/Colony のAR移行 ✅

- `_hives` / `_colonies` インメモリdictをHiveStore + HiveAggregate に移行
- Hive/Colony投影をGET APIの読み取り元に接続
- サーバー再起動後のデータ復元テスト追加
- **コミット**: `2959bf2`, `c5ccb89`

#### M1-2: Beekeeper全ハンドラ実装 ✅

- `handle_create_hive`, `handle_create_colony` — イベント発行、AR保存
- `handle_list_hives`, `handle_list_colonies` — AR投影から取得
- `handle_get_status` — AR/投影から実データ取得
- `handle_approve`, `handle_reject` — Requirement状態遷移
- `handle_emergency_stop` — Run/Task緊急停止
- `_ask_user` — VS Code拡張通知（M2で完成）
- **コミット**: `5e84f4b`

</details>

---

## 3. 開発マイルストーン（現在〜今後）

### M2: 接続（信頼できる組み合わせにする） ✅ 完了

**目標**: コンポーネント間を実際に接続し、エンドツーエンドで動作することを検証する。

#### M2-0: Sentinel Hornet ✅ 完了

- コアモジュール (`sentinel_hornet/monitor.py`)
- 4検出パターン実装（ループ/暴走/コスト/セキュリティ）
- Colony強制停止フロー (`sentinel.alert_raised` → `colony.suspended`)
- 設定ベース閾値 (`hiveforge.config.yaml`)
- **コミット**: `c942f65`, `522013e`

#### M2-1: VS Code拡張のAPI接続 ✅ 完了

| タスク | 内容 | 状態 |
|--------|------|------|
| M2-1-a | `hiveCommands.ts` — createHive/closeHive → API呼び出し | ✅ 実装済 |
| M2-1-b | `colonyCommands.ts` — createColony/startColony/completeColony → API | ✅ 実装済 |
| M2-1-c | `client.ts` — Hive/Colony API メソッド追加 | ✅ 実装済 |
| M2-1-d | エラーハンドリング | ✅ 実装済 |
| M2-1-e | TypeScriptコンパイル確認 | ✅ 確認済 |
| M2-1-f | 動作確認テスト | ✅ 完了 |

**完了条件**:
- VS Code拡張からHive/Colonyの作成・取得・終了ができる ✅
- API接続失敗時にユーザーへ適切なエラー通知が出る ✅

> **テスト**: `test_vscode_extension_api.py` (13テスト) でHive/Colony CRUD・エラーハンドリングを検証。

#### M2-2: Beekeeper → Queen Bee → Worker Bee統合 ✅ 完了

| タスク | 内容 | 状態 |
|--------|------|------|
| M2-2-a | `hiveforge chat` でBeekeeper経由のHive/Colony作成が動作 | ✅ 完了 |
| M2-2-b | Beekeeper → Queen Bee へのタスク委譲 | ✅ 完了 |
| M2-2-c | Worker Bee実行結果がARに記録 → 投影で確認可能 | ✅ 完了 |
| M2-2-d | 承認フロー（Requirement → approve/reject）がE2Eで動作 | ✅ 完了 |

**完了条件**:
- `hiveforge chat "ECサイトのログインページを作成"` で全チェーンが動作
- 全イベントがARに永続化される

> **注**: M2-2-a〜d全サブタスク実装完了。完了条件の確認はLLM APIキー設定後に実施。

#### M2-3: MCP Server ↔ Beekeeper連携 ✅ 完了

| タスク | 内容 | 状態 |
|--------|------|------|
| M2-3-a | Copilot Chat の `@hiveforge` → Beekeeper直結 | ✅ 完了 |
| M2-3-b | MCP経由のHive/Colony操作がAR永続化 | ✅ 完了 |

**M2-3-a 実装内容**:
- `chatHandler.ts`: VS Code Chat Participant (`@hiveforge`) を実装。`/status`, `/hives` コマンド + 自由文メッセージ送信
- `beekeeper.py` (API route): FastAPI `/beekeeper/send_message`, `/status`, `/approve`, `/reject` エンドポイント
- MCP Server dispatch: `send_message`, `get_beekeeper_status`, `approve`, `reject` → BeekeeperMCPServer委譲
- **テスト**: `test_beekeeper_api.py` (19テスト), `test_mcp_server.py::TestDispatchBeekeeperTools` (6テスト)

#### M2-4: LiteLLM統合（LLM統一インターフェース） ✅ 完了

| タスク | 内容 | 状態 |
|--------|------|------|
| M2-4-a | LLMClient→LiteLLM SDK移行（client.py書換え） | ✅ 完了 |
| M2-4-b | config拡張（13プロバイダー対応、api_base/fallback/num_retries） | ✅ 完了 |
| M2-4-c | テスト書換え（litellm.acompletion モック化） | ✅ 完了 |
| M2-4-d | hiveforge.config.yaml/ドキュメント更新 | ✅ 完了 |

**変更内容**:
- LLMClientをhttpx直接呼出しからLiteLLM SDK (`litellm.acompletion`) に全面移行
- OpenAI/Anthropic個別実装を削除し、LiteLLMの統一OpenAI互換I/Oに一本化
- 依存: `openai` + `anthropic` → `litellm>=1.40.0`（openai/anthropicは推移的依存として残存）
- 13プロバイダー対応: openai, azure, anthropic, ollama, ollama_chat, bedrock, vertex_ai, openrouter, huggingface, together_ai, groq, deepseek, litellm_proxy
- ローカル開発: Ollama + Qwen3-Coder-Next でコスト削減可能

**責務分界**:
- **LiteLLMに委譲**: モデル抽象化、プロバイダー間フォーマット変換、リトライ/フォールバック、コスト追跡
- **HiveForge保持**: Swarming Protocol、Honeycomb学習、Guard Bee L2、Sentinel Hornet、Waggle Dance、エージェント固有レートリミッター

---

### M3: 適応的協調（v1.5コア機能）

**目標**: Swarming Protocol, Guard Bee, Honeycomb を実装し、「学習するシステム」の基盤を構築する。

> **設計参照**: [コンセプト_v6.md](コンセプト_v6.md) §3-7

#### M3-1: Honeycomb（ハニカム）

**優先度: 高** — 学習基盤、KPI計算の前提

| タスク | 内容 | 対象ファイル |
|--------|------|-------------|
| M3-1-a | Episode データモデル定義 | `core/honeycomb/models.py` |
| M3-1-b | HoneycombStore 永続化（JSONL） | `core/honeycomb/store.py` |
| M3-1-c | 失敗分類 (FailureClass) 列挙型定義 | `core/honeycomb/models.py` |
| M3-1-d | Episode 記録API | `core/honeycomb/recorder.py` |
| M3-1-e | KPI算出（Honeycomb集計） | `core/honeycomb/kpi.py` |
| M3-1-f | Episode → AR イベント連携 | `core/events.py` |

**完了条件**:
- Run/Task の完了時に Episode が Honeycomb に自動記録される
- 失敗時に FailureClass が分類される
- 5つのKPI（Correctness, Repeatability, Lead Time, Incident Rate, Recurrence Rate）が算出可能

#### M3-2: Swarming Protocol Engine（分蜂プロトコル）

**優先度: 高** — 適応的Colony編成の中核

| タスク | 内容 | 対象ファイル |
|--------|------|-------------|
| M3-2-a | Swarming特徴量 (SwarmingFeatures) モデル定義 | `core/swarming/models.py` |
| M3-2-b | Colonyテンプレート定義 (Speed/Balanced/Quality/Recovery) | `core/swarming/templates.py` |
| M3-2-c | 特徴量→テンプレート選択ロジック | `core/swarming/engine.py` |
| M3-2-d | Beekeeperへの統合（タスク分析→Swarming評価→提案） | `beekeeper/server.py` |
| M3-2-e | 設定ファイルのテンプレートカスタマイズ | `hiveforge.config.yaml` |

**完了条件**:
- タスクの特徴量から自動的にテンプレートが選択される
- Beekeeperがユーザーにテンプレート選択を提案する
- 4テンプレート全てのテストが存在する

#### M3-3: Guard Bee（門番蜂 / 品質検証エージェント）

**優先度: 中** — Evidence-first原則の実装

| タスク | 内容 | 対象ファイル |
|--------|------|-------------|
| M3-3-a | Guard Bee データモデル | `guard_bee/models.py` | ✅ |
| M3-3-b | 検証ルール定義フレームワーク | `guard_bee/rules.py` | ✅ |
| M3-3-c | 検証実行エンジン | `guard_bee/verifier.py` | ✅ |
| M3-3-d | 合格/差戻しフロー | `guard_bee/verifier.py` | ✅ |
| M3-3-e | Honeycomb との連携（検証結果記録） | `guard_bee/verifier.py` | ✅ |
| M3-3-f | MCP / API エンドポイント | `api/routes/guard_bee.py` | ✅ |

**完了条件**:
- Colonyの成果物がGuard Beeによって検証される
- 証拠（diff, テスト結果, カバレッジ）に基づいて合格/差戻しが判定される
- 検証結果がHoneycombに記録される

#### M3-4: Forager Bee（採餌蜂 / 探索的テスト・影響分析） ✅ 完了

**優先度: 中** — Guard Bee完了後

| タスク | 内容 | 状態 |
|--------|------|------|
| M3-4-a | 変更影響グラフ構築（依存関係・呼び出し・イベント・設定の展開） | ✅ |
| M3-4-b | 含意シナリオ生成（正常系交差・境界値・順序違い・同時操作等） | ✅ |
| M3-4-c | 探索実行エンジン（シナリオベース統合テスト、状態機械パスカバレッジ） | ✅ |
| M3-4-d | 違和感検知（期待値差分・過去Run比較・副作用検出・性能回帰） | ✅ |
| M3-4-e | Guard Bee連携（ForagerReport → Guard Bee判定入力） | ✅ |

**完了条件**:
- コード変更から影響範囲グラフが自動構築される
- 含意シナリオが生成され、探索実行できる
- ForagerReportがGuard Beeに入力され品質判定に活用される

**コミット**: `f78bb68` (47テスト)

#### M3-5: Referee Bee（審判蜂 / 自動採点・生存選抜） ✅ 完了

**優先度: 中** — Forager Bee完了後

> v1.5.2で導入。「大量生成→自動検証→生存選抜」パラダイムの中核コンポーネント。
> N案候補を多面的に自動採点し、上位候補のみをGuard Beeに渡す。

| タスク | 内容 | 状態 |
|--------|------|------|
| M3-5-a | スコアリングエンジン実装（5指標: Correctness/Robustness/Consistency/Security/Latency） | ✅ |
| M3-5-b | Differential Testing実装（候補間・旧実装との出力差分比較） | ✅ |
| M3-5-c | トーナメント選抜ロジック（上位K件選抜、単一案スキップ） | ✅ |
| M3-5-d | RefereeReport Pydanticモデル + ARイベント記録 | ✅ |
| M3-5-e | Guard Bee連携（RefereeReport → Guard Bee判定入力） | ✅ |

**完了条件**:
- N案候補を5次元スコアで自動採点できる
- 候補間のDifferential Testingが動作する
- RefereeReportがGuard Beeに入力され品質判定に活用される
- 単一案の場合はReferee Beeがスキップされる

**コミット**: `5ae3442` (35テスト)

#### M3-6: Sentinel Hornet拡張（KPI監視 + 執行アクション） ✅ 完了

**優先度: 中** — 既存Sentinel Hornetの機能拡張

> Sentinel Hornet は検出と執行を一体で担当する（分離しない）。
> ロールバック・隔離の執行アクションを追加する。

| タスク | 内容 | 状態 |
|--------|------|------|
| M3-6-a | KPI劣化検出パターンの追加（Honeycomb連携） | ✅ |
| M3-6-b | ロールバックアクションの実装 | ✅ |
| M3-6-c | 隔離アクションの実装 | ✅ |
| M3-6-d | 新検出パターン・執行アクションのテスト追加 | ✅ |

**完了条件**:
- KPI劣化をHoneycombデータから検出できる
- 3つの執行アクション（停止[M2-0実装済] / ロールバック[新規] / 隔離[新規]）が動作
- 既存の全検出パターンテストが引き続き通る

**コミット**: `d51bc60` (14テスト追加)

#### M3-7: Waggle Dance（ワグルダンス / 構造化I/O検証） ✅ 完了

**優先度: 低** — M3-1〜M3-3完了後

| タスク | 内容 | 状態 |
|--------|------|------|
| M3-7-a | 通信メッセージのPydanticスキーマ定義 | ✅ |
| M3-7-b | 検証ミドルウェアの実装 | ✅ |
| M3-7-c | 検証エラーのARイベント記録 | ✅ |

**完了条件**:
- エージェント間の全通信がWaggle Danceを通過する
- スキーマ違反が自動検出・記録される

**コミット**: `942dfc3` (20テスト)

#### M3-8: Scout Bee（偵察蜂 / 編成最適化） ✅ 完了

**優先度: 低** — Honeycombに十分なデータが蓄積されてから

| タスク | 内容 | 状態 |
|--------|------|------|
| M3-8-a | 類似エピソード検索ロジック | ✅ |
| M3-8-b | テンプレート成功率分析 | ✅ |
| M3-8-c | Beekeeperへの最適化提案統合 | ✅ |

**完了条件**:
- Honeycombの過去Episodeから類似タスクのテンプレート推薦ができる
- コールドスタート時のデフォルトテンプレート適用が動作する（AGENTS.md §3 安全側フォールバック）

**コミット**: `3e2ce9b` (23テスト)

---

### M4: 自律（自律的タスク分解）

**目標**: LLMによるタスク分解を実装し、システムの本来の価値を実現する。

#### M4-1: Queen Bee タスク分解

| タスク | 内容 |
|--------|------|
| M4-1-a | `_plan_tasks()` のLLMタスク分解実装 |
| M4-1-b | タスク依存関係の解析と並列実行判定 |
| M4-1-c | 分解結果の妥当性検証（Guard Bee連携） |
| M4-1-d | 分解タスクの承認フロー（ActionClass連携） |

**完了条件**:
- 抽象的な目標を複数の具体タスクに分解できる
- 分解結果がARイベントとして記録される
- Guard Bee が分解の妥当性を検証する

✅ **M4-1 完了** (2025-07 / 1947テスト通過)

#### M4-2: LLM Orchestrator

| タスク | 内容 |
|--------|------|
| M4-2-a | エージェント間のコンテキスト共有 |
| M4-2-b | 複数Worker Beeの並列実行 |
| M4-2-c | 実行結果の集約とQueen Beeへの報告 |

**完了条件**:
- 複数Worker Beeが並列にタスク実行、結果がColony単位で集約される

✅ **M4-2 完了** (2025-07 / 1983テスト通過)
- M4-2-a: TaskResult + TaskContext（コンテキスト共有）
- M4-2-b: ColonyOrchestrator（層別並列実行）
- M4-2-c: ColonyResult + ColonyResultBuilder（結果集約）

---

### M5: 運用品質（プロダクション準備）

| タスク | 内容 | ステータス |
|--------|------|-----------|
| M5-1a | API認証ミドルウェア（X-API-Key / Bearer Token） | ✅ 完了 |
| M5-1b | 入力バリデーション強化（MCP + APIルート） | ✅ 完了 |
| M5-2 | パフォーマンス計測・最適化 | ✅ ベンチマーク基盤完了 |
| M5-3 | CI/CD強化（3ジョブ分割、カバレッジゲート96%） | ✅ 完了 |
| M5-4 | KPIダッシュボード（Hive Monitor Webview統合） | 未着手 |
| M5-5 | サンプルプロジェクト作成 | 未着手 |
| M5-6 | ユーザードキュメント完成 | 未着手 |

#### M5-1a 実装詳細
- `src/hiveforge/api/auth.py`: `verify_api_key` FastAPI依存
- X-API-Key ヘッダー + Authorization: Bearer トークン
- `secrets.compare_digest` でタイミング攻撃防止
- 除外パス: `/health`, `/docs`, `/redoc`, `/openapi.json`
- `auth.enabled: false`（デフォルト）で既存挙動に影響なし

#### M5-1b 実装詳細
- MCP全ハンドラに空文字・範囲バリデーション追加
- API `events.py` に Query 制約（limit, direction, max_depth）
- 23テストで全バリデーション網羅

#### M5-3 実装詳細
- GitHub Actions を3並列ジョブに分割: lint / test / vscode-extension
- テスト二重実行を解消
- `--cov-fail-under=96` でカバレッジゲート強制
- README.md に CIバッジ追加

#### M5-2 実装詳細
- `pytest-benchmark>=4.0.0` 導入（`pyproject.toml` dev依存に追加）
- `tests/test_benchmark.py`: 15件のベンチマーク（compute_hash, parse_event, to_jsonl, AR append/replay, Projection構築, HoneycombStore）
- ベンチマークは `@pytest.mark.benchmark` で通常テストから分離（`--benchmark-disable` デフォルト）
- 実行: `pytest tests/test_benchmark.py -m benchmark --benchmark-enable`
- ベースライン計測値:
  - parse_event: 4.8μs (209K ops/s)
  - compute_hash: 8.4μs (119K ops/s)
  - AR append: 201μs (5K ops/s)
  - AR replay 1000件: 6.4ms (155 ops/s)

---

### M1-残: 基盤品質改善（並行作業）

> M1のうち未完了項目。他マイルストーンと並行して進められる。

#### M1-3: 型安全性の確保

| タスク | 内容 |
|--------|------|
| M1-3-a〜f | 各モジュールの mypy --strict エラー解消 |

**完了条件**: `mypy --strict src/hiveforge/` がエラー 0

#### M1-4: カバレッジ改善

| タスク | 内容 |
|--------|------|
| M1-4-a〜c | 低カバレッジファイルのテスト補強 |

**完了条件**: 全体カバレッジ 93% 以上 → ✅ 達成済み (96.29%)

---

## 4. 優先順位（2026-02-08 更新）

M1〜M4完了。M2全サブタスク完了（M2-0〜M2-4）。M5一部着手済み。

```
     高
      │
      │  ════════ 次: 運用品質 ════════
      │  M5-4 (KPIダッシュボード)    ← Webview統合
      │  M5-5 (サンプルプロジェクト)  ← ドキュメント整備
      │  M5-6 (ユーザードキュメント)  ← GA準備
      │  M1-3 (型安全)              ← 長期信頼性（並行）
     低
```

<details>
<summary>完了済みマイルストーン（クリックで展開）</summary>

| マイルストーン | 完了内容 |
|---------------|---------|
| M4-1 | タスク分解 — TaskPlanner LLMタスク分解 |
| M4-2 | LLM Orchestrator — ColonyOrchestrator + ExecutionPipeline |
| M5-1 | セキュリティ — 認証+バリデーション |
| M5-2 | パフォーマンス — ベンチマーク基盤構築済み |
| M5-3 | CI/CD — 3ジョブ+カバレッジゲート |
| M2-0〜M2-4 | 統合パス確立 — Beekeeper→Queen→Worker E2E, Chat Participant, LiteLLM, GitHub Projection |
| P-02 | incident_rate — Sentinel Hornet介入の直接計測 |
| S-03 | Forager _run_single — AgentRunner統合 |

</details>
> - ✅ M2-1-f完了: test_vscode_extension_api.py (13テスト) + test_beekeeper_api.py (19テスト)
> - ✅ P-02解消: `_calc_incident_rate()` — Sentinel Hornet介入の直接計測実装。Episode.sentinel_intervention_count追加

---

## 5. ドキュメント整合方針

### 5.1 信頼できる情報源（Single Source of Truth）

| 情報 | 正の情報源 |
|------|-----------|
| テスト件数/カバレッジ | `pytest` / `pytest --cov` 実行結果 |
| フェーズ進捗 | 本計画 (DEVELOPMENT_PLAN_v2.md) |
| 設計思想 | コンセプト_v6.md |
| 詳細設計（状態機械/イベント型/プロトコル） | v5-hive-design.md |
| API仕様 | FastAPI自動生成 `/docs` |
| 実装ステータス | コード + テスト |

### 5.2 ドキュメント構成

| ドキュメント | 役割 | 記述レベル |
|---|---|---|
| [コンセプト_v6.md](コンセプト_v6.md) | **なぜ**: 設計思想・ビジョン | 概念・メタファー |
| [v5-hive-design.md](design/v5-hive-design.md) | **何を**: 詳細設計・スキーマ | 正式な仕様 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | **今どう**: 実装の現況 | 実装の事実 |
| **本書** | **次に何**: 開発計画 | タスク・優先度 |
| [QUICKSTART.md](QUICKSTART.md) | **使い方**: セットアップ手順 | 手順書 |
| [GIT_WORKFLOW.md](GIT_WORKFLOW.md) | **Git運用**: ブランチ・Worktree・PRゲート | 運用規約 |
| [AGENTS.md](../AGENTS.md) | **開発原則**: TDD, コミット規約 | ガイドライン |

### 5.3 アーカイブ済み

| ドキュメント | 移動先 | 理由 |
|-------------|--------|------|
| コンセプト_v5.md | `docs/archive/` | v6に統合 |
| DEVELOPMENT_PLAN_v1.md | `docs/archive/` | v2に更新 |
| IMPLEMENTATION_STATUS.md | `docs/archive/` | 古い数値 |
| ROADMAP.md | `docs/archive/` | 計画に統合 |
| SESSION_STATUS.md | `docs/archive/` | セッション記録 |
| TECH_DEBT.md | `docs/archive/` | M1に統合 |
| phase1-issues.md | `docs/archive/` | 歴史的参照 |
| コンセプト_v3.md | `docs/archive/` | 歴史的参照 |
| コンセプト_v4.md | `docs/archive/` | 歴史的参照 |

---

## 6. リスクと前提

| リスク | 影響 | 緩和策 |
|--------|------|--------|
| Swarming特徴量の精度 | テンプレート選択の品質 | 初期はルールベース、Honeycomb蓄積後にデータ駆動 |
| Honeycombのデータ量 | Scout Bee精度 | コールドスタート時はBalancedデフォルト |
| Guard Bee検証の厳格さ | 開発速度への影響 | 検証レベルをテンプレートごとに可変 |
| Forager Bee探索範囲 | 過剰な探索によるコスト増大 | 影響グラフの深さ制限、Guard Beeとの分業で範囲を限定 |
| Referee Beeスコア計算コスト | N案×5指標の計算量 | Nの上限設定、軽量指標から段階的に導入 |
| LLMタスク分解の品質 | 不確実性 | Guard Beeによる分解結果の検証 |

---

## 7. 完了したらどうなるか

### M2完了時 — 「信頼できる組み合わせ」（α版）

- VS CodeからHive/Colony操作が実際に動作する
- `hiveforge chat` で全エージェントチェーンが動く
- 全操作がARに記録され追跡可能

### M3完了時 — 「学習するシステム」（β版）

- タスク特性に応じた適応的Colony編成
- 成果物の品質が証拠ベースで検証される
- 変更の影響範囲がForager Beeで自動探索され、潜在的不整合がGuard Beeに証拠として提供される
- **N案並列生成 → Referee Bee自動採点 → Guard Bee最終判定** の選抜パイプラインが動作する
- 実行履歴から学習し、KPIが改善傾向を示す
- SOPがフィードバックループで進化する

### M4完了時 — 「自律的な開発支援」

- 抽象的な目標から具体タスクへの自動分解
- 複数Worker Beeの並列実行
- Guard Bee + Swarming Protocol + Honeycomb の統合による高品質な自律動作

### M5完了時 — 「プロダクション品質」（v1.5 GA）

- セキュリティ・安定性が確保されている
- KPIダッシュボードで健全性が可視化
- CI/CDが完全自動化されている

---

## 8. 技術的負債一覧（2026-02-11 精査）

> **残存負債のみ**を表示。解消済み項目は折りたたみ内に移動。

### 8.1 残存負債

#### 暫定ロジック（残存）

| # | ファイル | 箇所 | 現状 | 改善タイミング |
|---|---------|------|------|---------------|
| P-05 | `vlm/analyzer.py:78` | UI要素抽出 | キーワードマッチングによる簡易実装 | 必要時 |

#### 将来拡張ノート（コード内コメント）

| # | ファイル | コメント |
|---|---------|---------|
| N-01 | `core/swarming/engine.py:22` | 「将来的にHoneycombデータ駆動に移行可能」 |
| N-02 | `core/models/action_class.py:70` | `params` 引数は現在未使用（将来拡張用） |

### 8.2 解消済み負債

<details>
<summary>解消済み項目一覧（クリックで展開）</summary>

#### ハードコード・仮定 — 全件解消 (H-01〜H-08)

| # | 箇所 | 解消内容 |
|---|------|---------|
| H-01 | `scout_bee/matcher.py` 特徴量レンジ | `FEATURE_MIN`/`FEATURE_MAX` 定数に抽出、docstring明記 |
| H-02 | `scout_bee/matcher.py` 欠損特徴量 | `FEATURE_DEFAULT` 定数に抽出（中間値自動計算） |
| H-03 | `scout_bee/scout.py` デフォルトテンプレート | AGENTS.md §3 準拠のコメント明記 |
| H-04 | `core/rate_limiter.py` トークン上限 | docstring にGPT-4 Tier-1根拠を明記、config上書き方法を文書化 |
| H-05 | `core/rate_limiter.py` 不明モデルデフォルト | AGENTS.md §3 safe-side fallback コメント追加 |
| H-06 | `core/models/action_class.py` 不明ツール | AGENTS.md §3 safe-side fallback コメント追加 |
| H-07 | `vlm/ollama_client.py` 画像入力 | `_resolve_image_to_base64()` に明示的バリデーション追加、不正入力で `ValueError` |
| H-08 | `llm/prompts.py` システムプロンプト | `hiveforge.prompts/` パッケージに集約・英語化 |

#### クリティカルスタブ — 全件解消

| # | 箇所 | 解消内容 |
|---|------|---------|
| S-01 | `queen_bee/planner.py` `_plan_tasks()` | TaskPlanner でLLMタスク分解＋依存分析実装済 (M4-1) |
| S-02 | `beekeeper/server.py` `_ask_user()` | asyncio.Future ベース非同期実装済 (M2-2) |
| S-03 | `forager_bee/explorer.py` `_run_single()` | AgentRunner統合済 |

#### 暫定ロジック — 全件解消

| # | 箇所 | 解消内容 |
|---|------|---------|
| P-01 | `_calc_correctness()` | Guard Bee実装反映済 |
| P-02 | `_calc_incident_rate()` | Sentinel介入の直接計測実装済 |
| P-03 | `_calculate_kpi_scores()` | correctness/incident_rate算出済 |
| P-04 | デッドロック検出 | DFSベースの任意長サイクル検出に置換済 |

#### インメモリストア — 全件解消

| # | 箇所 | 解消内容 |
|---|------|---------|
| M-01 | InterventionStore | JSONL永続化導入済 |
| M-02 | get_intervention_store() | InterventionStore共有、getter/setterパターン |
| M-03 | ConferenceStore | JSONL永続化対応済 |

</details>

---

## 9. Git ワークフロー

Colony ベースの並列開発を安全かつ効率的に回すための Git 運用規約を策定済み。

**詳細**: [GIT_WORKFLOW.md](GIT_WORKFLOW.md)

### 概要

| 項目 | 内容 |
|------|------|
| ブランチモデル | `master` / `develop` / `feat/<hive>/<colony>/<ticket>-<slug>` / `fix/…` / `hotfix/…` / `exp/…` |
| Worktree | Colony 単位で `git worktree add`、上限 3 |
| Rebase/Merge | 個人→rebase、共有→merge、develop→master は `merge --no-ff` |
| PR ゲート | `guard-l1`（Lint/Unit）、`guard-l2`（設計整合）、`forager-regression`、`sentinel-safety` |
| GitHub Projection | AR イベント → GitHub Issue 同期（コード変更は PR、タスク進捗は Issue） |

### 関連コンポーネント

- **Guard Bee**: PR ゲート L1/L2 の CI ジョブとして動作
- **Forager Bee**: 変更影響グラフに基づく回帰テスト
- **Sentinel Hornet**: トークン上限・セキュリティパターン検出
- **GitHub Projection** (`core/github/`): AR→GitHub Issue 同期
