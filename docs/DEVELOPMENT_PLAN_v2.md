# HiveForge 開発計画 v2

> **策定日**: 2026-02-08
> **前版**: [DEVELOPMENT_PLAN_v1.md](archive/DEVELOPMENT_PLAN_v1.md) — 2026-02-07策定
> **トリガー**: v1.5コンセプト（Swarming Protocol, Guard Bee, Honeycomb等）の導入に伴い計画を再編
> **コンセプト**: [コンセプト_v6.md](コンセプト_v6.md)

---

## 1. 現状の事実認定（2026-02-08 時点）

### 1.1 計測済みメトリクス

| 指標 | 実測値 | 備考 |
|------|--------|------|
| **ユニットテスト** | `pytest` で確認 | 固定値は記載しない（CIで自動取得） |
| **カバレッジ** | `pytest --cov` で確認 | 同上 |
| **Lint (Ruff)** | ✅ All passed | — |

> テスト件数・カバレッジは**計測値のみを正とし**、ドキュメントに固定値を書かない。

### 1.2 コンポーネント別の実装実態

| コンポーネント | ステータス | 詳細 |
|---------------|-----------|------|
| **Hive Core** (イベント, AR, 状態機械) | ✅ 完了 | 47 EventType, 5状態機械, ハッシュ連鎖 |
| **Hive/Colony AR永続化** | ✅ M1-1完了 | HiveStore + HiveAggregate, JSONL永続化 |
| **API Server** (FastAPI REST) | ✅ 完了 | Hive/Colony CRUD が AR永続化と接続済み |
| **MCP Server** (Copilot連携) | ✅ 完了 | 全ツール実装・テスト済 |
| **CLI** | ✅ 完了 | `hiveforge chat` 等 |
| **Beekeeper server** | ✅ M1-2完了 | 全ハンドラ実装済（イベントソーシング連携） |
| **Beekeeper handler** | ✅ 完了 | — |
| **Queen Bee** | ⚠️ スタブ | `_plan_tasks()` が固定1タスク返却 |
| **Worker Bee** | ✅ 完了 | ツール実行, リトライ, Trust |
| **Sentinel Hornet** | ✅ M2-0完了 | 4検出パターン (ループ/暴走/コスト/セキュリティ) |
| **VS Code拡張** (コマンド) | 🔄 M2-1進行中 | Hive/Colony操作のAPI接続コード作成済、コンパイル未確認 |
| **VS Code拡張** (TreeView) | ✅ 完了 | Activity Hierarchy API連動 |
| **VS Code拡張** (Hive Monitor) | ✅ 完了 | リアルタイムWebview |
| **Agent UI / VLM / VLM Tester** | ✅ 完了 | — |
| **Swarming Protocol Engine** | ❌ 未実装 | v1.5で新規追加 |
| **Guard Bee** | ❌ 未実装 | v1.5で新規追加 |
| **Honeycomb** | ❌ 未実装 | v1.5で新規追加 |
| **Scout Bee** | ❌ 未実装 | v1.5で新規追加 |
| **Forager Bee** | ❌ 未実装 | v1.5.1で新規追加 |
| **Waggle Dance** | ❌ 未実装 | v1.5で新規追加 |
| **KPI Calculator** | ❌ 未実装 | v1.5で新規追加 |
| **LLM Orchestrator** | ❌ 未実装 | M4で実装予定 |

---

## 2. マイルストーン体系

### 2.1 全体像

```
M1 (基盤固め)  → M2 (接続)    → M3 (適応的協調) → M4 (自律)    → M5 (運用)
 ■■■■■■■■■■     ■■■■░░░░░░     ░░░░░░░░░░         ░░░░░░░░░░     ░░░░░░░░░░
 完了              進行中         v1.5 新規          タスク分解      プロダクション
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

#### M2-1: VS Code拡張のAPI接続 🔄 進行中

| タスク | 内容 | 状態 |
|--------|------|------|
| M2-1-a | `hiveCommands.ts` — createHive/closeHive → API呼び出し | ✅ 実装済 |
| M2-1-b | `colonyCommands.ts` — createColony/startColony/completeColony → API | ✅ 実装済 |
| M2-1-c | `client.ts` — Hive/Colony API メソッド追加 | ✅ 実装済 |
| M2-1-d | エラーハンドリング | ✅ 実装済 |
| M2-1-e | TypeScriptコンパイル確認 | ⬜ 未確認 |
| M2-1-f | 動作確認テスト | ⬜ 未実施 |

**完了条件**:
- VS Code拡張からHive/Colonyの作成・取得・終了ができる
- API接続失敗時にユーザーへ適切なエラー通知が出る

#### M2-2: Beekeeper → Queen Bee → Worker Bee統合

| タスク | 内容 |
|--------|------|
| M2-2-a | `hiveforge chat` でBeekeeper経由のHive/Colony作成が動作 |
| M2-2-b | Beekeeper → Queen Bee へのタスク委譲 |
| M2-2-c | Worker Bee実行結果がARに記録 → 投影で確認可能 |
| M2-2-d | 承認フロー（Requirement → approve/reject）がE2Eで動作 |

**完了条件**:
- `hiveforge chat "ECサイトのログインページを作成"` で全チェーンが動作
- 全イベントがARに永続化される

#### M2-3: MCP Server ↔ Beekeeper連携

| タスク | 内容 |
|--------|------|
| M2-3-a | Copilot Chat の `@hiveforge` → Beekeeper直結 |
| M2-3-b | MCP経由のHive/Colony操作がAR永続化 |

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
| M3-3-a | Guard Bee データモデル | `guard_bee/models.py` |
| M3-3-b | 検証ルール定義フレームワーク | `guard_bee/rules.py` |
| M3-3-c | 検証実行エンジン | `guard_bee/verifier.py` |
| M3-3-d | 合格/差戻しフロー | `guard_bee/verifier.py` |
| M3-3-e | Honeycomb との連携（検証結果記録） | `guard_bee/verifier.py` |
| M3-3-f | MCP / API エンドポイント | `api/routes/guard_bee.py` |

**完了条件**:
- Colonyの成果物がGuard Beeによって検証される
- 証拠（diff, テスト結果, カバレッジ）に基づいて合格/差戻しが判定される
- 検証結果がHoneycombに記録される

#### M3-4: Forager Bee（採餌蜂 / 探索的テスト・影響分析）

**優先度: 中** — Guard Bee完了後

| タスク | 内容 |
|--------|------|
| M3-4-a | 変更影響グラフ構築（依存関係・呼び出し・イベント・設定の展開） |
| M3-4-b | 含意シナリオ生成（正常系交差・境界値・順序違い・同時操作等） |
| M3-4-c | 探索実行エンジン（シナリオベース統合テスト、状態機械パスカバレッジ） |
| M3-4-d | 違和感検知（期待値差分・過去Run比較・副作用検出・性能回帰） |
| M3-4-e | Guard Bee連携（ForagerReport → Guard Bee判定入力） |

**完了条件**:
- コード変更から影響範囲グラフが自動構築される
- 含意シナリオが生成され、探索実行できる
- ForagerReportがGuard Beeに入力され品質判定に活用される

#### M3-5: Sentinel Hornet拡張（KPI監視 + 執行アクション）

**優先度: 中** — 既存Sentinel Hornetの機能拡張

> Sentinel Hornet は検出と執行を一体で担当する（分離しない）。
> ロールバック・隔離の執行アクションを追加する。

| タスク | 内容 |
|--------|------|
| M3-5-a | KPI劣化検出パターンの追加（Honeycomb連携） |
| M3-5-b | ロールバックアクションの実装 |
| M3-5-c | 隔離アクションの実装 |
| M3-5-d | 新検出パターン・執行アクションのテスト追加 |

**完了条件**:
- KPI劣化をHoneycombデータから検出できる
- 3つの執行アクション（停止/ロールバック/隔離）が動作
- 既存の全検出パターンテストが引き続き通る

#### M3-6: Waggle Dance（ワグルダンス / 構造化I/O検証）

**優先度: 低** — M3-1〜M3-3完了後

| タスク | 内容 |
|--------|------|
| M3-6-a | 通信メッセージのPydanticスキーマ定義 |
| M3-6-b | 検証ミドルウェアの実装 |
| M3-6-c | 検証エラーのARイベント記録 |

**完了条件**:
- エージェント間の全通信がWaggle Danceを通過する
- スキーマ違反が自動検出・記録される

#### M3-7: Scout Bee（偵察蜂 / 編成最適化）

**優先度: 低** — Honeycombに十分なデータが蓄積されてから

| タスク | 内容 |
|--------|------|
| M3-7-a | 類似エピソード検索ロジック |
| M3-7-b | テンプレート成功率分析 |
| M3-7-c | Beekeeperへの最適化提案統合 |

**完了条件**:
- Honeycombの過去Episodeから類似タスクのテンプレート推薦ができる
- コールドスタート時のフォールバックが動作する

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

#### M4-2: LLM Orchestrator

| タスク | 内容 |
|--------|------|
| M4-2-a | エージェント間のコンテキスト共有 |
| M4-2-b | 複数Worker Beeの並列実行 |
| M4-2-c | 実行結果の集約とQueen Beeへの報告 |

**完了条件**:
- 複数Worker Beeが並列にタスク実行、結果がColony単位で集約される

---

### M5: 運用品質（プロダクション準備）

| タスク | 内容 |
|--------|------|
| M5-1 | セキュリティ監査（API認証、入力検証） |
| M5-2 | パフォーマンス計測・最適化 |
| M5-3 | CI/CD強化（テスト・型チェック・カバレッジの自動化） |
| M5-4 | KPIダッシュボード（Hive Monitor Webview統合） |
| M5-5 | サンプルプロジェクト作成 |
| M5-6 | ユーザードキュメント完成 |

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

**完了条件**: 全体カバレッジ 93% 以上

---

## 4. 優先順位

```
     高
      │  M2-1 (VS Code API接続)     ← ユーザー体験（進行中）
      │  M2-2 (エージェント統合)     ← E2E動作
      │  M3-1 (Honeycomb)           ← v1.5学習基盤
      │  M3-2 (Swarming Protocol)   ← v1.5適応的編成
      │  M3-3 (Guard Bee)           ← v1.5品質検証
      │  M3-4 (Forager Bee)         ← v1.5探索的テスト
      │  M3-5 (Sentinel Hornet拡張) ← v1.5執行機能追加
      │  M4-1 (タスク分解)           ← 本来の価値提供
      │  M3-6 (Waggle Dance)       ← I/O構造化
      │  M3-7 (Scout Bee)           ← 最適化（データ蓄積後）
      │  M1-3 (型安全)              ← 長期信頼性（並行）
      │  M5   (運用品質)            ← プロダクション
     低
```

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
| LLMタスク分解の品質 | M4の不確実性 | Guard Beeによる分解結果の検証 |

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
