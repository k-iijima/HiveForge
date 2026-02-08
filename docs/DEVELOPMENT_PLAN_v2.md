# HiveForge 開発計画 v2

> **策定日**: 2026-02-08
> **前版**: [DEVELOPMENT_PLAN_v1.md](archive/DEVELOPMENT_PLAN_v1.md) — 2026-02-07策定
> **トリガー**: v1.5コンセプト（Swarming Protocol, Guard Bee, Honeycomb等）の導入に伴い計画を再編
> **コンセプト**: [コンセプト_v6.md](コンセプト_v6.md)

---

## 1. 現状の事実認定（2026-02-07 更新）

### 1.1 計測済みメトリクス

| 指標 | 実測値 | 備考 |
|------|--------|------|
| **ユニットテスト** | `pytest` で確認（参考: 1869件 @ 2026-02-08） | 固定値は記載しない（CIで自動取得） |
| **カバレッジ** | `pytest --cov` で確認 | 同上 |
| **Lint (Ruff)** | ✅ All passed | — |
| **EventType数** | 61 | `core/events/types.py` |

> テスト件数・カバレッジは**計測値のみを正とし**、ドキュメントに固定値を書かない。

### 1.2 コンポーネント別の実装実態

| コンポーネント | ステータス | 詳細 | 既知の制約 |
|---------------|-----------|------|------------|
| **Hive Core** (イベント, AR, 状態機械) | ✅ 完了 | 61 EventType, 5状態機械, ハッシュ連鎖 | — |
| **Hive/Colony AR永続化** | ✅ M1-1完了 | HiveStore + HiveAggregate, JSONL永続化 | — |
| **API Server** (FastAPI REST) | ✅ 完了 | Hive/Colony CRUD が AR永続化と接続済み | 認証ミドルウェア実装済 (`auth.enabled: false` がデフォルト) |
| **MCP Server** (Copilot連携) | ✅ 完了 | 全ツール実装・テスト済 | — |
| **CLI** | ✅ 完了 | `hiveforge chat` 等 | mypy strict未対応 (M1-3) |
| **Beekeeper server** | ✅ M1-2完了 | 全ハンドラ実装済 | **`_ask_user()` はスタブ** — ユーザー入力を実際に待たず即応答を返す (→ M2-2で解消) |
| **Beekeeper handler** | ✅ 完了 | — | — |
| **Queen Bee** | ✅ M4-1/M4-2完了 | LLMタスク分解・並列実行・ゲート統合実装済 | TaskPlanner + ColonyOrchestrator + ExecutionPipeline |
| **Worker Bee** | ✅ 完了 | ツール実行, リトライ, Trust | — |
| **Sentinel Hornet** | ✅ M3-6完了 | 7検出パターン + KPI劣化検出 + ロールバック/隔離 | `_calc_incident_rate()` は失敗エピソード比率で算出（§8 P-02参照） |
| **VS Code拡張** (コマンド) | ✅ M2-1完了 | API接続コード作成済、TSコンパイル+Lint確認済 | **実際のE2E動作テスト未実施** (M2-1-f) |
| **VS Code拡張** (TreeView) | ✅ 完了 | Activity Hierarchy API連動 | — |
| **VS Code拡張** (Hive Monitor) | ✅ 完了 | リアルタイムWebview | — |
| **Agent UI / VLM / VLM Tester** | ✅ 完了 | — | VLM画像入力のbase64判定は仮定ベース |
| **Swarming Protocol Engine** | ✅ M3-2完了 | 3軸特徴量、4テンプレート、Beekeeper統合、Config対応 | ルールベース選択、将来Honeycombデータ駆動に移行予定 |
| **Guard Bee** | ✅ M3-3完了 | Evidence-first品質検証、2層検証(L1/L2)、5組込ルール | — |
| **Honeycomb** | ✅ M3-1完了 | Episodeモデル、JSONL永続化、KPI算出 | `correctness` / `incident_rate` は Episode 単位で算出済み (§8 P-01〜P-03 解消済) |
| **Scout Bee** | ✅ M3-8完了 | 類似エピソード検索、テンプレート成功率分析、最適化提案 | 特徴量レンジ1〜5を固定仮定、コールドスタート時は`balanced`固定 |
| **Forager Bee** | ✅ M3-4完了 | 変更影響グラフ、シナリオ生成、探索実行、違和感検知 | **`_run_single()` はスタブ** — 全シナリオを無条件pass (→ M4-2でLLM統合後に実装) |
| **Referee Bee** | ✅ M3-5完了 | 5次元スコアリング、Differential Testing、トーナメント選抜 | — |
| **Waggle Dance** | ✅ M3-7完了 | Pydanticスキーマ検証、バリデーションミドルウェア、ARイベント記録 | — |
| **KPI Calculator** | ✅ M3-1完了 | HoneycombのKPICalculatorとして実装済 | P-02 `_calc_incident_rate()` のみ残存 (§8参照) |
| **LLM Orchestrator** | ✅ M4-2完了 | ColonyOrchestrator（層別並列実行）+ ColonyResult（結果集約）+ ExecutionPipeline（ゲート統合） | — |
| **介入・エスカレーション** | ✅ 完了 | API/MCPハンドラ実装済、InterventionStore JSONL永続化 | — |

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

### M2: 接続（信頼できる組み合わせにする）

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
| M2-1-f | 動作確認テスト | ⬜ 未実施 |

**完了条件**:
- VS Code拡張からHive/Colonyの作成・取得・終了ができる
- API接続失敗時にユーザーへ適切なエラー通知が出る

#### M2-2: Beekeeper → Queen Bee → Worker Bee統合 🚧 進行中

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

#### M2-3: MCP Server ↔ Beekeeper連携 🚧 進行中

| タスク | 内容 | 状態 |
|--------|------|------|
| M2-3-a | Copilot Chat の `@hiveforge` → Beekeeper直結 | ⬜ 未着手 |
| M2-3-b | MCP経由のHive/Colony操作がAR永続化 | ✅ 完了 |

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
- コールドスタート時のフォールバックが動作する

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
| M5-2 | パフォーマンス計測・最適化 | 未着手 |
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

M1〜M4完了。M5（運用品質）一部着手済み（M5-1/M5-3完了）。
M2-2 サブタスク全完了、M2-3-b完了。

**レビュー指摘**: M5の残項目（パフォーマンス・KPIダッシュボード等）を進める前に、M2-2/M2-3の統合パスを完成させる必要がある。エージェントチェーンが一気通貫で動作しない限り、M5の運用品質評価は基盤不足。

```
     高
      │
      │  ════════ 完了済み ════════
      │  M4-1 (タスク分解)           ✅ 完了
      │  M4-2 (LLM Orchestrator)    ✅ 完了
      │  M5-1 (セキュリティ)         ✅ 完了（認証+バリデーション）
      │  M5-3 (CI/CD)               ✅ 完了（3ジョブ+カバレッジゲート）
      │  M2-2 (エージェント統合)     ✅ 完了（Beekeeper→Queen→Worker E2E）
      │  M2-3-b (MCP→AR永続化)      ✅ 完了（Intervention系含む全操作永続化）
      │
      │  ════════ 最優先: 統合パス確立 ════════
      │  M2-3-a (Copilot↔Beekeeper)  ← 🔴 最優先: @hiveforge → Beekeeper直結
      │  M2-1-f (VS Code拡張E2E)     ← 🔴 UI入口の動作保証
      │
      │  ════════ 次点: 暫定ロジック解消 ════════
      │  P-02 (KPIインシデント率)    ← 🟡 Sentinel Hornet介入の直接計測
      │  S-03 (Forager _run_single)  ← 🟡 探索実行のLLM統合
      │
      │  ════════ その後: 運用品質 ════════
      │  M5-2 (パフォーマンス)       ← 統合パス確立後に着手
      │  M5-4 (KPIダッシュボード)    ← Webview統合
      │  M5-5 (サンプルプロジェクト)  ← ドキュメント整備
      │  M5-6 (ユーザードキュメント)  ← GA準備
      │  M1-3 (型安全)              ← 長期信頼性（並行）
     低
```

> **方針転換**: M2-2/M2-3を完了してエージェントチェーンのE2E動作を確立することが、
> M5（運用品質）の前提条件である。統合パスが通らない限り、運用品質の評価軸が作れない。
>
> **進捗**:
> - ✅ M2-2完了: `_ask_user()` 非同期化、Pipeline統合、承認フローE2E、チャットチェーンE2E
> - ✅ M2-3-b完了: 全MCP操作（Intervention系含む）がAR永続化
> - ⬜ M2-3-a残: Copilot Chat `@hiveforge` → Beekeeper直結
> - 🔴 M2-1-f未実施 → UIの動作保証なし

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
| LLMタスク分解の品質 | M4の不確実性 | Guard Beeによる分解結果の検証 |
| **統合パス未確立** | **M5運用品質の評価が不可能** | **M2-2/M2-3を最優先で完了** |
| **KPI暫定ロジック** | **Sentinel/Honeycombの判断精度** | **P-02解消を統合パス確立後に着手** |
| **VS Code拡張E2E未検証** | **UI入口の不具合残存リスク** | **M2-1-f完了を品質ゲートに設定** |

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

## 8. 技術的負債一覧（2026-02-07 精査 / 2026-02-08 更新）

> コードベース全体を精査し、スタブ・暫定実装・仮決め・ハードコード等をすべて列挙。
> 再開時にどこから手をつけるかが一目でわかることを目的とする。
> **2026-02-08 更新**: S-01, P-01, P-03, P-04, M-01〜M-03 を解消済みに更新。M4-1/M4-2完了を反映。

### 8.1 クリティカルスタブ（機能が実質的に動作しない）

| # | ファイル | 箇所 | 現状 | 解消マイルストーン |
|---|---------|------|------|-------------------|
| S-01 | ~~`queen_bee/server.py`~~ → `queen_bee/planner.py` | `_plan_tasks()` | ~~固定1タスク返却~~ → `TaskPlanner` でLLMタスク分解＋依存分析（`execution_order`）＋フォールバック実装済 | ✅ M4-1-a/b 解消 |
| S-02 | `beekeeper/server.py:728-734` | `_ask_user()` | ユーザー入力を実際に待たず即応答を返却 (`# TODO: VS Code拡張に通知してユーザー入力を待つ`) | M2-2 |
| S-03 | `forager_bee/explorer.py:43-52` | `_run_single()` | 全シナリオを無条件 `passed=True` で返却。実際のテスト実行にはLLM統合が必要 | M5以降 |

### 8.2 暫定ロジック（動作するが精度が不十分）

| # | ファイル | 箇所 | 現状 | 改善タイミング |
|---|---------|------|------|---------------|
| P-01 | `core/honeycomb/kpi.py:86-91` | `_calc_correctness()` | ~~「Guard Beeが未実装のため」コメント~~ → コメント修正済み。Guard Bee実装済を反映 | ✅ 解消 |
| P-02 | `core/honeycomb/kpi.py:129-134` | `_calc_incident_rate()` | 「Sentinel Hornet介入の直接計測は未実装」— 失敗系エピソード比率で代替 | M4以降 |
| P-03 | `core/honeycomb/recorder.py:174-178` | `_calculate_kpi_scores()` | ~~`lead_time`のみ計算~~ → `correctness`, `incident_rate` も Episode 単位で算出済み | ✅ 解消 |
| P-04 | `queen_bee/communication.py:253` | デッドロック検出 | ~~「簡易版」~~ → DFSベースの任意長サイクル検出に置換済み | ✅ 解消 |
| P-05 | `vlm/analyzer.py:78` | UI要素抽出 | キーワードマッチングによる簡易実装 | 必要時 |

### 8.3 インメモリストア（~~プロセス再起動で消失~~ → 全件解消済み）

| # | ファイル | 箇所 | 現状 | 解消方法 |
|---|---------|------|------|---------|
| M-01 | `mcp_server/handlers/intervention.py` | `InterventionStore` | ~~Phase 1 インメモリ~~ → `core/intervention/` に InterventionStore (JSONL永続化) を導入済み | ✅ 解消 |
| M-02 | `api/routes/interventions.py` | `get_intervention_store()` | ~~モジュール変数dict~~ → InterventionStore を共有、getter/setter パターンでテスト注入可能 | ✅ 解消 |
| M-03 | `core/state/conference.py:89` | `ConferenceStore` | ~~インメモリ dict~~ → `base_path` オプション追加、JSONL永続化対応済み | ✅ 解消 |

### 8.4 ハードコード・仮定

| # | ファイル | 箇所 | 現状 | 意図 |
|---|---------|------|------|------|
| H-01 | `scout_bee/matcher.py:54` | 特徴量レンジ | 1〜5 固定仮定 | Swarming特徴量の実態に合わせて変更可能 |
| H-02 | `scout_bee/matcher.py:65` | 欠損特徴量 | デフォルト3.0（中間値） | コールドスタート時の安全策 |
| H-03 | `scout_bee/scout.py:15-16` | デフォルトテンプレート | `_DEFAULT_TEMPLATE = "balanced"` | コールドスタート時のフォールバック |
| H-04 | `core/rate_limiter.py:37` | トークン上限 | `tokens_per_minute: int = 90000` (GPT-4想定) | 他モデルではconfigで上書き可能 |
| H-05 | `core/rate_limiter.py:273-278` | 不明モデル | 保守的デフォルト (RPM=20, TPM=40000) | 安全側に倒す設計 |
| H-06 | `core/models/action_class.py:80` | 不明ツール | `REVERSIBLE` として分類 | 安全側に倒す設計 |
| H-07 | `vlm/ollama_client.py:102` | 画像入力 | 文字列はbase64と仮定 | ファイルパス等の区別なし |
| H-08 | `llm/prompts.py:20-100` | システムプロンプト | YAML未設定時のインラインフォールバック | `default_prompts/`の設定で上書き可能 |

### 8.5 将来拡張ノート（コード内コメント）

| # | ファイル | コメント |
|---|---------|---------|
| N-01 | `core/swarming/engine.py:22` | 「将来的にHoneycombデータ駆動に移行可能」 |
| N-02 | `core/models/action_class.py:70` | `params` 引数は現在未使用（将来拡張用） |

### 8.6 優先度まとめ（2026-02-08 レビュー指摘反映）

| 優先度 | 項目 | 理由 |
|--------|------|------|
| ~~✅ 解消~~ | ~~S-01 `_plan_tasks()`~~ | TaskPlanner でLLMタスク分解＋依存分析実装済 (M4-1-a/b) |
| **🔴 最優先** | S-02 `_ask_user()` | M2-2の主目標。ユーザーインタラクション未接続。統合パスのボトルネック |
| **🔴 最優先** | M2-1-f VS Code拡張E2E | UI入口の動作保証がない。ユーザー操作点での品質未検証 |
| **🟡 次点** | P-02 `_calc_incident_rate()` | Sentinel Hornet/HoneycombのKPI精度に直結。暫定ロジックで運用監視の信頼性が低い |
| **🟡 次点** | S-03 `_run_single()` | Foragerの探索実行はスタブのまま。品質判定の根拠が不十分 |
| **🟢 低** | H-01〜H-08 ハードコード | 現時点で意図的な仮定。必要時にconfig化 |
| ~~✅ 解消~~ | ~~P-01, P-03, P-04~~ | KPIコメント修正・correctness/incident_rate算出・DFSデッドロック検出 |
| ~~✅ 解消~~ | ~~M-01〜M-03 インメモリ~~ | InterventionStore JSONL + ConferenceStore base_path |
