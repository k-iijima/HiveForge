# HiveForge アーキテクチャ設計書

このドキュメントでは、HiveForgeの**現在の実装状況**を説明します。

> **ドキュメントの役割分担**
>
> | ドキュメント | 役割 | 記述レベル |
> |---|---|---|
> | [コンセプト_v6.md](コンセプト_v6.md) | **なぜ**: 設計思想・ビジョン・ユースケース | 概念・メタファー |
> | [v5-hive-design.md](design/v5-hive-design.md) | **何を**: 詳細設計・スキーマ・プロトコル定義 | 正式な仕様（Single Source of Truth） |
> | **本書 (ARCHITECTURE.md)** | **今どうなっている**: 実装の現況・ディレクトリ構造 | 実装の事実 |
> | [DEVELOPMENT_PLAN_v2.md](DEVELOPMENT_PLAN_v2.md) | **次に何をする**: 開発計画・マイルストーン | タスク・優先度 |  
>
> 状態機械・イベント型・通信プロトコルの正式定義は [v5-hive-design.md](design/v5-hive-design.md) を参照。
> 本書は実装の現況を反映し、設計との乖離がある場合は明示します。

---

## 目次

1. [システム概要](#1-システム概要)
2. [コンポーネント構成](#2-コンポーネント構成)
3. [階層モデル（Hive/Colony）](#3-階層モデルhivecolony)
4. [データモデル](#4-データモデル)
5. [API仕様](#5-api仕様)
6. [状態機械](#6-状態機械)
7. [イベントシステム](#7-イベントシステム)
8. [因果リンク（Lineage）](#8-因果リンクlineage)
9. [ディレクトリ構造](#9-ディレクトリ構造)
10. [設定](#10-設定)
11. [開発計画・ゲート条件](#11-開発計画ゲート条件)
12. [今後の拡張](#12-今後の拡張)

---

## 1. システム概要

### 1.1 基本思想

HiveForgeは「**信頼できる部品を、信頼できる組み合わせ方をして、信頼できるシステムを作る**」という理念に基づいています。

### 1.2 コア原則

- **イベントソーシング**: 全ての状態変更をイベントとして記録
- **イミュータブル**: イベントは一度書き込まれたら変更不可
- **追跡可能性**: 任意の成果物から「なぜ」を遡及可能
- **制御可能性**: 状態機械による厳密な状態管理と緊急停止

### 1.3 アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────┐
│                         VS Code                              │
│  ┌──────────────────┐  ┌────────────────────────────────┐   │
│  │  GitHub Copilot  │  │  HiveForge Extension           │   │
│  │      Chat        │  │  ├─ Hive Monitor (Webview)     │   │
│  │  （対話・操作）   │  │  ├─ イベントログ (TreeView)    │   │
│  └────────┬─────────┘  │  └─ ステータスバー             │   │
│           │            └────────────────┬───────────────┘   │
└───────────┼─────────────────────────────┼───────────────────┘
            │ MCP                         │ HTTP
            ▼                             ▼
┌───────────────────────┐    ┌─────────────────────────────┐
│  HiveForge MCP Server │    │    HiveForge API Server     │
│  (stdio通信)          │    │    (FastAPI / REST)         │
└───────────┬───────────┘    └──────────────┬──────────────┘
            │                               │
            └──────────────┬────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│                   エージェント階層                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Beekeeper（養蜂家 / ファシリテーター）             │  │
│  │  - ユーザーとの主対話、複数Hiveの統括管理           │  │
│  └──────────────────────┬─────────────────────────────┘  │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐  │
│  │  Hive（プロジェクト）                               │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Sentinel Hornet（監視）                      │  │  │
│  │  │  - 暴走/ループ/コスト超過検出 → 強制停止      │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Guard Bee（最終品質判定）                 [M3-3] │  │  │
│  │  │  - 選抜案の証拠ベース合格/差戻し判定              │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Referee Bee（自動採点・選抜）             [M3-5] │  │  │
│  │  │  - N案候補の多面的スコアリング → 上位選抜        │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Forager Bee（探索的テスト）               [M3-4] │  │  │
│  │  │  - 影響グラフ探索・違和感検知 → Referee/Guardへ   │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌────────────┐  │  │
│  │  │Colony: UI/UX│ │Colony: API  │ │Colony:Infra│  │  │
│  │  │ Queen Bee   │ │ Queen Bee   │ │ Queen Bee  │  │  │
│  │  │ Worker Bee… │ │ Worker Bee… │ │ Worker Bee…│  │  │
│  │  └─────────────┘ └─────────────┘ └────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                           │
            ┌──────────────▼───────────────┐
            │         Hive Core            │
            │  ┌────────────────────────┐  │
            │  │   Akashic Record (AR)  │  │
            │  │   - イベント永続化     │  │
            │  │   - ハッシュ連鎖       │  │
            │  └────────────────────────┘  │
            │  ┌────────────────────────┐  │
            │  │    State Machines      │  │
            │  │   - Run / Task / Req   │  │
            │  │   - Hive / Colony      │  │
            │  └────────────────────────┘  │
            │  ┌────────────────────────┐  │
            │  │     Projections        │  │
            │  │   - イベント→状態     │  │
            │  └────────────────────────┘  │
            └──────────────────────────────┘
                           │
                           ▼
            ┌──────────────────────────────┐
            │      Vault (ファイルシステム)  │
            │  └── {run_id}/events.jsonl   │
            └──────────────────────────────┘
```

---

## 2. コンポーネント構成

### 2.1 コンポーネント一覧

| コンポーネント | 役割 | 実装状況 | 既知の制約 |
|----------------|------|----------|------------|
| **Hive Core** | イベント管理・状態機械・投影 | ✅ 完了 | — |
| **API Server** | REST API エンドポイント | ✅ 完了 | 認証は未有効化 (`auth.enabled: false`) |
| **MCP Server** | Copilot Chat連携 | ✅ 完了 | — |
| **CLI** | コマンドラインインターフェース | ✅ 完了 | mypy strict未対応 (M1-3) |
| **Beekeeper** | ユーザー窓口・Hive統括 | ✅ M1-2完了 | `_ask_user()` はスタブ (→ M2-2) |
| **Queen Bee** | Colony統括・タスク分解 | ✅ M4-1完了 | TaskPlannerによるLLMタスク分解＋依存分析実装済 |
| **Worker Bee** | タスク実行（MCPサブプロセス） | ✅ 完了 | — |
| **Sentinel Hornet** | Hive内監視・異常検出・強制停止 | ✅ M3-6完了 | 7検出パターン + KPI劣化検出 + ロールバック/隔離。`_calc_incident_rate()` は暫定ロジック |
| **Honeycomb** | 実行履歴・学習基盤 | ✅ M3-1完了 | `_calc_correctness()` / `_calc_incident_rate()` が暫定ロジック |
| **Swarming Protocol Engine** | タスク適応的Colony編成 | ✅ M3-2完了 | ルールベース選択。将来Honeycombデータ駆動に移行予定 |
| **Guard Bee** | Evidence-first品質検証 | ✅ M3-3完了 | 2層検証(L1/L2)、5組込ルール |
| **Forager Bee** | 探索的テスト・影響分析・違和感検知 | ✅ M3-4完了 | `_run_single()` はスタブ（全シナリオ無条件pass → M4-2） |
| **Referee Bee** | N案候補の多面的採点・生存選抜 | ✅ M3-5完了 | 5次元スコアリング、Differential Testing、トーナメント |
| **Scout Bee** | 過去実績に基づく編成最適化 | ✅ M3-8完了 | 特徴量レンジ1〜5固定仮定、コールドスタート時は`balanced`固定 |
| **Waggle Dance** | I/O構造化検証 | ✅ M3-7完了 | Pydanticスキーマ検証、バリデーションミドルウェア、ARイベント記録 |
| **LLM Orchestrator** | 自律的タスク分解・実行 | ✅ M4-2完了 | ColonyOrchestrator（並列実行）+ ExecutionPipeline（ゲート統合） |
| **VS Code拡張** (TreeView) | Activity階層表示 | ✅ 完了 | — |
| **VS Code拡張** (Hive Monitor) | リアルタイム活動可視化 | ✅ 完了 | — |
| **VS Code拡張** (コマンド) | Hive/Colony操作 | ✅ M2-1完了 | API接続コード作成済。E2E動作テスト未実施 (M2-1-f) |
| **介入・エスカレーション** | API/MCPハンドラ | ✅ 完了 | InterventionStore JSONL永続化、ConferenceStore JSONL永続化 |
| **Agent UI** | ブラウザ自動操作MCPサーバー | ✅ 完了 | — |
| **VLM** | 画像解析・画面認識 | ✅ 完了 | String画像入力のbase64判定は仮定ベース |
| **VLM Tester** | Playwright + VLMによるE2Eテスト | ✅ 完了 | — |
| **Silence Detector** | 沈黙検出 | ✅ 完了 | — |

> 各コンポーネントの詳細な実態とギャップは [DEVELOPMENT_PLAN_v2.md](DEVELOPMENT_PLAN_v2.md) §1.2 を参照。
> マイルストーン（M1〜M5）の記号は同計画の §3 に対応。
> 既知の制約の詳細は [DEVELOPMENT_PLAN_v2.md](DEVELOPMENT_PLAN_v2.md) §8 技術的負債一覧を参照。
>
> **重要な制約（2026-02-08 レビュー指摘）**:
> - 「✅ 完了」はユニットテスト＋API単体レベルの完成度を示す。**E2E統合パスは未検証**（M2-2/M2-3未着手）。
> - Beekeeper `_ask_user()`, Forager `_run_single()` のスタブにより、人間参加・探索実行の経路は未接続。
> - KPI算出ロジック（`_calc_incident_rate()`）が暫定版のため、運用監視の精度は限定的。
> - VS Code拡張はAPI接続コード完成だが E2E動作テスト未実施（M2-1-f）。

### 2.2 モジュール依存関係

```
hiveforge/
├── core/                  # コアモジュール（他から参照される）
│   ├── events/           # イベントモデル（M3-6でパッケージ化）
│   │   ├── base.py           # BaseEvent
│   │   ├── types.py          # EventType enum (61種)
│   │   ├── run.py            # Run関連イベント
│   │   ├── hive.py           # Hive/Colony関連イベント
│   │   ├── worker.py         # Worker Beeイベント
│   │   ├── decision.py       # Decisionイベント
│   │   ├── operation.py      # Operation Failure/Timeout
│   │   ├── guard.py          # Guard Beeイベント
│   │   ├── pipeline.py       # Pipelineイベント
│   │   ├── sentinel.py       # Sentinel Hornetイベント
│   │   ├── waggle.py         # Waggle Danceイベント
│   │   └── registry.py       # イベントレジストリ
│   ├── config.py         # 設定管理
│   ├── activity_bus.py   # Activity Bus
│   ├── lineage.py        # 因果リンク
│   ├── policy_gate.py    # ポリシーゲート
│   ├── rate_limiter.py   # レートリミッター
│   ├── intervention/     # 介入・エスカレーション永続化
│   │   ├── models.py         # 介入モデル
│   │   └── store.py          # InterventionStore (JSONL永続化)
│   ├── models/           # ドメインモデル
│   │   ├── action_class.py
│   │   └── project_contract.py
│   ├── ar/               # Akashic Record
│   │   ├── storage.py        # Run永続化
│   │   ├── projections.py    # Run状態投影
│   │   ├── hive_storage.py   # Hive/Colony永続化
│   │   └── hive_projections.py # Hive/Colony投影
│   ├── state/            # 状態機械
│   │   ├── machines.py        # Run/Task/Requirement SM
│   │   ├── projections.py     # 状態投影
│   │   ├── colony_progress.py # Colony進捗追跡
│   │   └── conference.py      # Conference状態
│   ├── honeycomb/        # 実行履歴・学習基盤 (M3-1)
│   │   ├── models.py         # Episode, KPIScore等
│   │   ├── store.py          # EpisodeStore (JSONL永続化)
│   │   ├── recorder.py       # EpisodeRecorder
│   │   └── kpi.py            # KPICalculator（lead_time他）
│   └── swarming/         # Swarming Protocol (M3-2)
│       ├── models.py         # SwarmingFeatures, SwarmingTemplate
│       ├── engine.py         # SwarmingEngine（テンプレート選択）
│       └── templates.py      # 4テンプレート定義
├── api/                   # REST API（coreに依存）
│   ├── server.py         # FastAPIアプリ
│   ├── dependencies.py   # 依存性注入（AppState）
│   ├── helpers.py        # 後方互換エクスポート
│   ├── models.py         # APIモデル
│   └── routes/           # エンドポイント
│       ├── runs.py       # Run関連
│       ├── tasks.py      # Task関連
│       ├── events.py     # Event関連
│       ├── requirements.py # Requirement関連
│       ├── hives.py      # Hive CRUD
│       ├── colonies.py   # Colony CRUD
│       ├── activity.py   # Activity API
│       ├── conferences.py # Conference API
│       ├── interventions.py # Intervention API
│       └── system.py     # ヘルスチェック等
├── mcp_server/            # MCP Server（coreに依存）
│   ├── server.py
│   ├── tools.py          # ツール定義
│   └── handlers/         # ハンドラー実装
├── beekeeper/             # Beekeeper層（core, llmに依存）
│   ├── server.py         # MCPサーバー
│   ├── handler.py        # コアハンドラー
│   ├── session.py        # セッション管理
│   ├── projection.py     # 状態投影
│   ├── conference.py     # Conference機能
│   ├── conflict.py       # 衝突検出
│   ├── escalation.py     # エスカレーション
│   ├── resolver.py       # 衝突解決
│   └── tool_definitions.py # ツール定義
├── queen_bee/             # Queen Bee層（core, llmに依存、M4実装済）
│   ├── server.py         # MCPサーバー
│   ├── planner.py        # TaskPlanner（LLMタスク分解・依存分析）(M4-1)
│   ├── orchestrator.py   # ColonyOrchestrator（層別並列実行）(M4-2)
│   ├── pipeline.py       # ExecutionPipeline（Guard Bee/承認ゲート統合）
│   ├── context.py        # TaskResult / TaskContext（コンテキスト共有）(M4-2)
│   ├── result.py         # ColonyResult / ColonyResultBuilder（結果集約）(M4-2)
│   ├── approval.py       # PlanApprovalGate（承認制御）(M4-1)
│   ├── communication.py  # エージェント間通信
│   ├── progress.py       # 進捗管理
│   ├── retry.py          # リトライ制御
│   └── scheduler.py      # Colonyスケジューラー
├── worker_bee/            # Worker Bee層（core, llmに依存）
│   ├── server.py         # MCPサーバー
│   ├── process.py        # タスク実行
│   ├── projections.py    # 投影
│   ├── retry.py          # リトライ制御
│   ├── tools.py          # ツール定義
│   └── trust.py          # Trust Level制御
├── sentinel_hornet/       # Sentinel Hornet (M2-0 + M3-6)
│   ├── __init__.py       # SentinelHornet公開API
│   └── monitor.py        # 7検出パターン + KPI劣化 + ロールバック/隔離
├── guard_bee/             # Guard Bee (M3-3)
│   ├── __init__.py
│   ├── models.py         # VerificationRequest, VerificationResult等
│   ├── rules.py          # 5組込ルール
│   ├── plan_rules.py     # プラン検証ルール
│   └── verifier.py       # 2層検証 (L1 structural / L2 semantic)
├── forager_bee/           # Forager Bee (M3-4)
│   ├── __init__.py
│   ├── models.py         # ImpactNode, Scenario等
│   ├── graph_builder.py  # 変更影響グラフ構築
│   ├── scenario_generator.py # シナリオ自動生成
│   ├── explorer.py       # 探索実行（_run_single はスタブ）
│   ├── anomaly_detector.py   # 違和感検知
│   └── reporter.py       # レポート生成
├── referee_bee/           # Referee Bee (M3-5)
│   ├── __init__.py
│   ├── models.py         # CandidateSolution, ScoreCard等
│   ├── scoring.py        # 5次元スコアリング
│   ├── diff_tester.py    # Differential Testing
│   ├── tournament.py     # トーナメント選抜
│   └── reporter.py       # 比較レポート
├── scout_bee/             # Scout Bee (M3-8)
│   ├── __init__.py
│   ├── models.py         # ScoutProposal等
│   ├── matcher.py        # 類似エピソード検索
│   ├── analyzer.py       # テンプレート成功率分析
│   └── scout.py          # 最適化提案生成
├── waggle_dance/          # Waggle Dance (M3-7)
│   ├── __init__.py
│   ├── models.py         # WaggleDanceSchema等
│   ├── validator.py      # Pydanticスキーマ検証
│   └── recorder.py       # ARイベント記録
├── llm/                   # LLM統合（coreに依存、LiteLLM SDK経由）
│   ├── client.py         # LLMクライアント（LiteLLM acompletion）
│   ├── runner.py         # AgentRunner
│   ├── tools.py          # LLMツール
│   ├── prompts.py        # プロンプト取得
│   ├── prompt_config.py  # プロンプト設定スキーマ
│   └── default_prompts/  # デフォルトプロンプトYAML
├── agent_ui/              # Agent UI MCPサーバー
│   ├── server.py         # サーバー本体
│   ├── session.py        # ブラウザセッション管理
│   ├── tools.py          # ツール定義
│   └── handlers.py       # ハンドラー実装
├── vlm/                   # VLM（画像解析）
│   ├── analyzer.py       # 画像分析
│   └── ollama_client.py  # Ollamaクライアント
├── vlm_tester/            # VLM Tester（E2Eテスト支援）
│   ├── server.py         # MCPサーバー
│   ├── playwright_mcp_client.py
│   ├── vlm_client.py
│   ├── hybrid_analyzer.py
│   └── ...               # その他分析・実行モジュール
├── silence.py             # 沈黙検出（coreに依存）
└── cli.py                 # CLI（api, mcp_serverに依存）
```

---

## 3. 階層モデル（Hive/Colony）

### 3.1 概念

HiveForgeは4層の階層構造でプロジェクトを管理します：

```
Hive（組織単位・プロジェクト）
 ├── Colony（作業チーム・目標単位）
 │    ├── Run（実行単位）
 │    │    ├── Task（タスク）
 │    │    └── Requirement（確認要請）
 │    └── Run
 └── Colony
```

### 3.2 Hive（巣）

**定義**: プロジェクト全体を管理する最上位の組織単位

| 属性 | 型 | 説明 |
|------|-----|------|
| `hive_id` | string | 一意識別子（ULID） |
| `name` | string | Hive名 |
| `description` | string? | 説明 |
| `status` | HiveState | `active` \| `idle` \| `closed` |

**状態遷移**（実装済み: `core/ar/projections.py`, `core/state/machines.py`）:
```
       ┌──────────┐
       │  ACTIVE   │◄──── COLONY_CREATED
       └────┬──┬───┘
  COLONY_   │  │ HIVE_CLOSED
  COMPLETED │  │
       ┌────▼──┼───┐
       │  IDLE  │   │
       └────┬──┘   │
  HIVE_     │      │
  CLOSED    │      │
       ┌────▼──────▼┐
       │  CLOSED     │
       └─────────────┘
```

**APIエンドポイント**:
- `POST /hives` - Hive作成
- `GET /hives` - Hive一覧
- `GET /hives/{hive_id}` - Hive詳細
- `POST /hives/{hive_id}/close` - Hive終了

**MCPツール**:
- `create_hive` - Hive作成
- `list_hives` - Hive一覧
- `get_hive` - Hive詳細
- `close_hive` - Hive終了

### 3.3 Colony（コロニー）

**定義**: 特定の目標を持つ作業グループ。複数のRunを含む。

| 属性 | 型 | 説明 |
|------|-----|------|
| `colony_id` | string | 一意識別子（ULID） |
| `hive_id` | string | 所属Hive ID |
| `name` | string | Colony名 |
| `goal` | string? | 目標説明 |
| `status` | ColonyState | `pending` \| `in_progress` \| `completed` \| `failed` \| `suspended` |

**状態遷移**（実装済み: `core/ar/projections.py`, `core/state/machines.py`）:
```
┌─────────┐
│ PENDING  │
└────┬─────┘
     │ COLONY_STARTED
     ▼
┌────────────┐     ┌───────────┐
│IN_PROGRESS │────►│ SUSPENDED │
└──┬──────┬──┘     └─────┬──┬──┘
   │      │              │  │
   │      │    (再開)◄────┘  │
   ▼      ▼                 ▼
┌────────┐ ┌────────┐ ┌────────┐
│COMPLETED│ │ FAILED │ │ FAILED │
└────────┘ └────────┘ └────────┘
```

> `SUSPENDED` 状態はSentinel Hornet（M2-0）により追加済み。
> Sentinel の異常検出 → `colony.suspended` イベント → Colony一時停止 → Beekeeper判断で再開/失敗。

**APIエンドポイント**:
- `POST /hives/{hive_id}/colonies` - Colony作成
- `GET /hives/{hive_id}/colonies` - Colony一覧
- `POST /colonies/{colony_id}/start` - Colony開始
- `POST /colonies/{colony_id}/complete` - Colony完了

**MCPツール**:
- `create_colony` - Colony作成
- `list_colonies` - Colony一覧
- `start_colony` - Colony開始
- `complete_colony` - Colony完了

### 3.4 Run-Colony紐付け

イベントには`colony_id`フィールドがあり、RunをColonyに紐付けます：

```python
class BaseEvent(BaseModel):
    colony_id: str | None = None  # 所属Colony ID
```

`RunColonyProjection`がColony→Runのマッピングを管理し、`ColonyProgressTracker`がRun完了時にColonyの自動完了判定を行います。

---

## 4. データモデル

### 4.1 BaseEvent（イベント基底クラス）

すべてのイベントの基底となるイミュータブルなモデル:

```python
class BaseEvent(BaseModel):
    model_config = {"frozen": True}  # イミュータブル
    
    id: str                    # ULID形式のイベントID
    type: EventType            # イベント種別
    timestamp: datetime        # 発生時刻（UTC）
    run_id: str | None         # 関連するRunのID
    task_id: str | None        # 関連するTaskのID
    colony_id: str | None      # 関連するColonyのID（v5追加）
    actor: str                 # イベント発生者
    payload: dict[str, Any]    # イベントペイロード
    prev_hash: str | None      # 前イベントのハッシュ（チェーン用）
    parents: list[str]         # 親イベントのID（因果リンク用）
    
    @computed_field
    def hash(self) -> str:     # JCS正規化 + SHA-256
        ...
```

### 4.2 イベント型一覧

主要なイベント型を以下に示します（全量は `core/events/types.py` の `EventType` enum を参照）:

| カテゴリ | イベント型 | 説明 |
|----------|------------|------|
| **Run** | `run.started` | Run開始 |
| | `run.completed` / `run.failed` / `run.aborted` | Run終了系 |
| **Task** | `task.created` / `task.assigned` / `task.progressed` | Task進行系 |
| | `task.completed` / `task.failed` / `task.blocked` / `task.unblocked` | Task終了系 |
| **Requirement** | `requirement.created` / `requirement.approved` / `requirement.rejected` | 確認要請 |
| **Hive/Colony** | `hive.created` / `hive.closed` | Hiveライフサイクル |
| | `colony.created` / `colony.started` / `colony.suspended` / `colony.completed` / `colony.failed` | Colonyライフサイクル |
| **Conference** | `conference.started` / `conference.ended` | 会議ライフサイクル |
| **Decision** | `decision.proposal.created` / `decision.recorded` / `decision.applied` / `decision.superseded` | 意思決定 |
| **Conflict** | `conflict.detected` / `conflict.resolved` | Colony間衝突 |
| **Intervention** | `intervention.user_direct` / `intervention.queen_escalation` / `intervention.beekeeper_feedback` | 直接介入・エスカレーション |
| **Worker** | `worker.assigned` / `worker.started` / `worker.progress` / `worker.completed` / `worker.failed` | Worker Bee実行 |
| **Operation** | `operation.timeout` / `operation.failed` | 標準失敗・タイムアウト |
| **Sentinel Hornet** | `sentinel.alert_raised` / `sentinel.report` | 基本アラート・レポート (M2-0) |
| | `sentinel.rollback` / `sentinel.quarantine` / `sentinel.kpi_degradation` | 執行アクション (M3-6) |
| **Guard Bee** | `guard.verification_requested` / `guard.passed` / `guard.conditional_passed` / `guard.failed` | Evidence-first検証 (M3-3) |
| **Waggle Dance** | `waggle_dance.validated` / `waggle_dance.violation` | I/O構造化検証 (M3-7) |
| **Pipeline** | `pipeline.started` / `pipeline.completed` | 実行パイプライン |
| | `plan.validation_failed` / `plan.approval_required` / `plan.fallback_activated` | プラン検証・承認・フォールバック |
| **LLM** | `llm.request` / `llm.response` | LLM連携 |
| **System** | `system.heartbeat` / `system.error` / `system.silence_detected` / `system.emergency_stop` | システム |
| **Unknown** | （任意の文字列） | 前方互換用（`UnknownEvent`として読み込み） |

> 全61 EventType。イベント型の正式なスキーマ定義・payload仕様は [v5-hive-design.md §3](design/v5-hive-design.md) を参照。

### 4.3 RunProjection（状態投影）

イベントから導出される現在状態:

```python
class RunProjection:
    id: str                           # Run ID
    goal: str                         # 目標
    state: RunState                   # 状態
    started_at: datetime | None       # 開始時刻
    completed_at: datetime | None     # 完了時刻
    tasks: dict[str, TaskProjection]  # タスク一覧
    requirements: dict[str, RequirementProjection]  # 要件一覧
    event_count: int                  # イベント数
    last_heartbeat: datetime | None   # 最終ハートビート
```

### 4.4 TaskProjection

```python
class TaskProjection:
    id: str
    title: str
    state: TaskState        # pending/assigned/in_progress/completed/failed/blocked
    progress: int           # 0-100
    assignee: str | None
    retry_count: int
    created_at: datetime
```

---

## 5. API仕様

### 5.1 REST API エンドポイント

#### System

| Method | Path | 説明 |
|--------|------|------|
| GET | `/health` | ヘルスチェック |

#### Runs

| Method | Path | 説明 |
|--------|------|------|
| POST | `/runs` | Run開始 |
| GET | `/runs` | Run一覧取得 |
| GET | `/runs/{run_id}` | Run詳細取得 |
| POST | `/runs/{run_id}/complete` | Run完了 |
| POST | `/runs/{run_id}/emergency-stop` | 緊急停止 |
| POST | `/runs/{run_id}/heartbeat` | ハートビート送信 |

##### Run完了の詳細

`POST /runs/{run_id}/complete` は未完了タスクがある場合は400エラーを返します。

**リクエストボディ:**
```json
{ "force": true }  // オプション
```

**動作:**
- `force=false`（デフォルト）: 未完了タスクがあればエラー
- `force=true`: 未完了タスクを自動キャンセル、未解決の確認要請を自動却下

**レスポンス例:**
```json
{
  "status": "completed",
  "run_id": "01HZZ...",
  "cancelled_task_ids": ["01HZZ..."],
  "cancelled_requirement_ids": ["01HZZ..."]
}
```

##### 緊急停止の詳細

`POST /runs/{run_id}/emergency-stop` はRunを即座に停止します。

**動作:**
- 未完了タスクを全て失敗状態に
- 未解決の確認要請を全て却下
- Runを`ABORTED`状態に遷移

#### Tasks

| Method | Path | 説明 |
|--------|------|------|
| POST | `/runs/{run_id}/tasks` | Task作成 |
| GET | `/runs/{run_id}/tasks` | Task一覧取得 |
| POST | `/runs/{run_id}/tasks/{task_id}/complete` | Task完了 |
| POST | `/runs/{run_id}/tasks/{task_id}/fail` | Task失敗 |

#### Events

| Method | Path | 説明 |
|--------|------|------|
| GET | `/runs/{run_id}/events` | イベント一覧取得 |
| GET | `/runs/{run_id}/events/{event_id}/lineage` | 因果リンク取得 |

### 5.2 MCP ツール一覧

| ツール | 説明 | パラメータ |
|--------|------|------------|
| `start_run` | Run開始 | `goal` |
| `get_run_status` | 状態取得 | `run_id?` |
| `create_task` | Task作成 | `title`, `description?` |
| `assign_task` | Task割り当て | `task_id` |
| `report_progress` | 進捗報告 | `task_id`, `progress`, `message?` |
| `complete_task` | Task完了 | `task_id`, `result?` |
| `fail_task` | Task失敗 | `task_id`, `error`, `retryable?` |
| `create_requirement` | 要件作成 | `description`, `options?` |
| `complete_run` | Run完了 | `summary?`, `force?` |
| `heartbeat` | ハートビート | `message?` |
| `emergency_stop` | 緊急停止 | `reason`, `scope?` |
| `get_lineage` | 因果リンク取得 | `event_id`, `direction?`, `max_depth?` |

---

## 6. 状態機械

Hive/ColonyStateMachine は §3.2, §3.3 を参照。Run/Task/Requirement の詳細な遷移ルールは [v5-hive-design.md §2](design/v5-hive-design.md) に正式定義があります。

以下は実装済みの状態機械の概要です（`core/state/machines.py`）:

### 6.1 RunStateMachine

```
RUNNING → COMPLETED | FAILED | ABORTED
```

### 6.2 TaskStateMachine

```
PENDING → ASSIGNED → IN_PROGRESS → COMPLETED | FAILED
                                  → BLOCKED → IN_PROGRESS (復帰)
```

### 6.3 RequirementStateMachine

```
PENDING → APPROVED | REJECTED
```

---

## 7. イベントシステム

### 7.1 イベント永続化

イベントはJSONL形式でファイルに追記保存:

```
Vault/
└── {run_id}/
    └── events.jsonl    # 1行1イベント
```

### 7.2 ハッシュ連鎖

各イベントは前のイベントのハッシュを保持し、改ざん検知を可能に:

```
event[0] ─hash─▶ event[1] ─hash─▶ event[2] ─hash─▶ ...
           │              │              │
        prev_hash      prev_hash      prev_hash
```

### 7.3 ハッシュ計算

1. イベントデータから`hash`フィールドを除外
2. JCS (RFC 8785) で正規化
3. SHA-256でハッシュ計算

```python
def compute_hash(data: dict[str, Any]) -> str:
    data_for_hash = {k: v for k, v in data.items() if k != "hash"}
    data_for_hash = _serialize_value(data_for_hash)  # datetime等を変換
    canonical = jcs.canonicalize(data_for_hash)
    return hashlib.sha256(canonical).hexdigest()
```

---

## 8. 因果リンク（Lineage）

### 8.1 概要

各イベントは`parents`フィールドで親イベントを参照し、因果関係を記録:

```python
class TaskCreatedEvent(BaseEvent):
    parents: list[str] = ["run_started_event_id"]  # 親イベントのID
```

### 8.2 探索方向

| 方向 | 説明 | 実装方式 |
|------|------|----------|
| `ancestors` | 祖先（親方向） | `parents[]`を再帰的に辿る |
| `descendants` | 子孫（子方向） | 全イベント走査 |
| `both` | 両方向 | 上記の組み合わせ |

### 8.3 APIレスポンス例

```json
{
  "event_id": "01HZZ...",
  "ancestors": ["01HZY...", "01HZX..."],
  "descendants": ["01J00...", "01J01..."],
  "truncated": false
}
```

### 8.4 制限

- `max_depth`: 探索深度制限（デフォルト: 10）
- `truncated`: 制限により切り詰められた場合`true`

---

## 9. ディレクトリ構造

### 9.1 プロジェクト構造

```
HiveForge/
├── src/hiveforge/           # メインパッケージ
│   ├── __init__.py
│   ├── cli.py               # CLIエントリポイント
│   ├── silence.py           # 沈黙検出
│   ├── core/                # コアモジュール
│   │   ├── config.py        # 設定管理
│   │   ├── events/          # イベントモデル (61 EventType)
│   │   │   ├── base.py          # BaseEvent
│   │   │   ├── types.py         # EventType enum
│   │   │   ├── run.py           # Run/Task/Requirement
│   │   │   ├── hive.py          # Hive/Colony/Conference/Conflict
│   │   │   ├── worker.py        # Worker Beeイベント
│   │   │   ├── decision.py      # Decisionイベント
│   │   │   ├── operation.py     # Failure/Timeout
│   │   │   ├── guard.py         # Guard Beeイベント
│   │   │   ├── pipeline.py      # Pipelineイベント
│   │   │   ├── sentinel.py      # Sentinel Hornetイベント
│   │   │   ├── waggle.py        # Waggle Danceイベント
│   │   │   └── registry.py      # イベントレジストリ
│   │   ├── activity_bus.py  # Activity Bus
│   │   ├── lineage.py       # 因果リンク
│   │   ├── policy_gate.py   # ポリシーゲート
│   │   ├── rate_limiter.py  # レートリミッター
│   │   ├── intervention/    # 介入・エスカレーション永続化
│   │   │   ├── models.py        # 介入モデル
│   │   │   └── store.py         # InterventionStore (JSONL)
│   │   ├── models/          # ドメインモデル
│   │   │   ├── action_class.py
│   │   │   └── project_contract.py
│   │   ├── ar/              # Akashic Record
│   │   │   ├── storage.py       # Run永続化
│   │   │   ├── projections.py   # Run状態投影
│   │   │   ├── hive_storage.py  # Hive/Colony永続化
│   │   │   └── hive_projections.py # Hive/Colony投影
│   │   ├── state/           # 状態機械
│   │   │   ├── machines.py       # Run/Task/Requirement SM
│   │   │   ├── projections.py    # 状態投影
│   │   │   ├── colony_progress.py # Colony進捗追跡
│   │   │   └── conference.py     # Conference状態
│   │   ├── honeycomb/       # 実行履歴・学習基盤 (M3-1)
│   │   │   ├── models.py        # Episode, KPIScore等
│   │   │   ├── store.py         # EpisodeStore (JSONL永続化)
│   │   │   ├── recorder.py      # EpisodeRecorder
│   │   │   └── kpi.py           # KPICalculator
│   │   └── swarming/        # Swarming Protocol (M3-2)
│   │       ├── models.py        # SwarmingFeatures, Template
│   │       ├── engine.py        # SwarmingEngine
│   │       └── templates.py     # 4テンプレート定義
│   ├── api/                 # REST API
│   │   ├── server.py        # FastAPIアプリ
│   │   ├── dependencies.py  # 依存性注入（AppState）
│   │   ├── helpers.py       # 後方互換エクスポート
│   │   ├── models.py        # APIモデル
│   │   └── routes/          # エンドポイント
│   │       ├── runs.py
│   │       ├── tasks.py
│   │       ├── events.py
│   │       ├── requirements.py
│   │       ├── hives.py         # Hive CRUD
│   │       ├── colonies.py      # Colony CRUD
│   │       ├── activity.py      # Activity API
│   │       ├── conferences.py   # Conference API
│   │       ├── interventions.py # Intervention API
│   │       └── system.py
│   ├── mcp_server/          # MCP Server
│   │   ├── server.py
│   │   ├── tools.py         # ツール定義
│   │   └── handlers/        # ハンドラー実装
│   ├── beekeeper/           # Beekeeper層
│   │   ├── server.py        # MCPサーバー
│   │   ├── handler.py       # コアハンドラー
│   │   ├── session.py       # セッション管理
│   │   ├── projection.py    # 状態投影
│   │   ├── conference.py    # Conference機能
│   │   ├── conflict.py      # 衝突検出
│   │   ├── escalation.py    # エスカレーション
│   │   ├── resolver.py      # 衝突解決
│   │   └── tool_definitions.py # ツール定義
│   ├── queen_bee/           # Queen Bee層 (M4実装済)
│   │   ├── server.py        # MCPサーバー
│   │   ├── planner.py       # TaskPlanner（LLMタスク分解）(M4-1)
│   │   ├── orchestrator.py  # ColonyOrchestrator（並列実行）(M4-2)
│   │   ├── pipeline.py      # ExecutionPipeline（ゲート統合）
│   │   ├── context.py       # TaskResult / TaskContext (M4-2)
│   │   ├── result.py        # ColonyResult / ColonyResultBuilder (M4-2)
│   │   ├── approval.py      # PlanApprovalGate（承認制御）(M4-1)
│   │   ├── communication.py # エージェント間通信
│   │   ├── progress.py      # 進捗管理
│   │   ├── retry.py         # リトライ制御
│   │   └── scheduler.py     # Colony スケジューラー
│   ├── worker_bee/          # Worker Bee層
│   │   ├── server.py        # MCPサーバー
│   │   ├── process.py       # タスク実行
│   │   ├── projections.py   # 投影
│   │   ├── retry.py         # リトライ制御
│   │   ├── tools.py         # ツール定義
│   │   └── trust.py         # Trust Level制御
│   ├── sentinel_hornet/     # Sentinel Hornet (M2-0 + M3-6)
│   │   └── monitor.py       # 7パターン + KPI劣化 + ロールバック/隔離
│   ├── guard_bee/           # Guard Bee (M3-3)
│   │   ├── models.py        # VerificationRequest/Result
│   │   ├── rules.py         # 5組込ルール
│   │   ├── plan_rules.py    # プラン検証ルール
│   │   └── verifier.py      # 2層検証 (L1/L2)
│   ├── forager_bee/         # Forager Bee (M3-4)
│   │   ├── models.py        # ImpactNode, Scenario等
│   │   ├── graph_builder.py # 変更影響グラフ
│   │   ├── scenario_generator.py # シナリオ生成
│   │   ├── explorer.py      # 探索実行
│   │   ├── anomaly_detector.py   # 違和感検知
│   │   └── reporter.py      # レポート生成
│   ├── referee_bee/         # Referee Bee (M3-5)
│   │   ├── models.py        # ScoreCard, Tournament等
│   │   ├── scoring.py       # 5次元スコアリング
│   │   ├── diff_tester.py   # Differential Testing
│   │   ├── tournament.py    # トーナメント選抜
│   │   └── reporter.py      # 比較レポート
│   ├── scout_bee/           # Scout Bee (M3-8)
│   │   ├── models.py        # ScoutProposal等
│   │   ├── matcher.py       # 類似エピソード検索
│   │   ├── analyzer.py      # テンプレート成功率分析
│   │   └── scout.py         # 最適化提案
│   ├── waggle_dance/        # Waggle Dance (M3-7)
│   │   ├── models.py        # WaggleDanceSchema等
│   │   ├── validator.py     # Pydanticスキーマ検証
│   │   └── recorder.py      # ARイベント記録
│   ├── llm/                 # LLM統合（LiteLLM SDK経由）
│   │   ├── client.py        # LLMクライアント（LiteLLM acompletion）
│   │   ├── runner.py        # AgentRunner
│   │   ├── tools.py         # LLMツール
│   │   ├── prompts.py       # プロンプト取得
│   │   ├── prompt_config.py # プロンプト設定スキーマ
│   │   └── default_prompts/ # デフォルトプロンプトYAML
│   ├── agent_ui/            # Agent UI MCPサーバー
│   │   ├── server.py        # サーバー本体
│   │   ├── session.py       # ブラウザセッション管理
│   │   ├── tools.py         # ツール定義
│   │   └── handlers.py      # ハンドラー実装
│   ├── vlm/                 # VLM（画像解析）
│   │   ├── analyzer.py      # 画像分析
│   │   └── ollama_client.py # Ollamaクライアント
│   └── vlm_tester/          # VLM Tester（E2Eテスト支援）
│       ├── server.py        # MCPサーバー
│       ├── playwright_mcp_client.py
│       ├── vlm_client.py
│       ├── hybrid_analyzer.py
│       ├── action_executor.py
│       ├── local_analyzers.py
│       ├── screen_capture.py
│       └── vlm_providers.py
├── tests/                   # Pythonテスト（`pytest` で件数確認）
│   ├── conftest.py
│   ├── test_*.py            # 各モジュール対応テスト
│   └── e2e/                 # E2Eテスト
│       ├── test_hiveforge_visual.py
│       ├── test_hiveforge_extension.py
│       └── test_hive_flow.py
├── vscode-extension/        # VS Code拡張
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── extension.ts
│       ├── client.ts        # APIクライアント
│       ├── commands/        # コマンド実装
│       │   ├── index.ts
│       │   ├── hiveCommands.ts
│       │   ├── colonyCommands.ts
│       │   ├── runCommands.ts
│       │   ├── taskCommands.ts
│       │   ├── requirementCommands.ts
│       │   ├── decisionCommands.ts
│       │   └── filterCommands.ts
│       ├── providers/       # TreeViewプロバイダー
│       ├── views/           # Webviewパネル
│       │   ├── dashboardPanel.ts
│       │   ├── hiveMonitorPanel.ts
│       │   ├── hiveTreeView.ts
│       │   ├── agentMonitorPanel.ts
│       │   └── requirementDetailView.ts
│       ├── utils/           # ユーティリティ
│       └── test/            # テスト
│           ├── client.test.ts
│           ├── colonyCommands.test.ts
│           ├── hiveCommands.test.ts
│           ├── html.test.ts
│           ├── vscode-mock.ts
│           └── vscode-shim.ts
├── docs/                    # ドキュメント
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_PLAN_v2.md
│   ├── QUICKSTART.md
│   ├── VLM_TESTER.md
│   ├── コンセプト_v6.md
│   ├── design/              # 詳細設計
│   │   └── v5-hive-design.md
│   └── archive/             # 旧ドキュメント
├── Vault/                   # イベントログ（gitignore）
├── AGENTS.md                # AI開発ガイドライン
├── pyproject.toml           # Pythonプロジェクト設定
├── hiveforge.config.yaml    # 実行時設定
├── docker-compose.yml       # Docker設定
└── Dockerfile
```

### 9.2 Vault構造

```
Vault/
├── {run_id}/                # Run単位のイベントログ（v4互換）
│   └── events.jsonl         # 1行1イベント（JSONL形式）
├── hive-{hive_id}/          # Hive関連イベント
│   └── events.jsonl
├── meta-decisions/          # 意思決定メタデータ
│   └── events.jsonl
└── ...                      # 今後拡張予定（→ M1-1 AR移行）
```

> **設計との差異**: [v5-hive-design.md §4](design/v5-hive-design.md) では `Vault/hives/{hive_id}/colonies/{colony_id}/` 階層を定義しているが、
> 現在の実装は上記のフラット構造。M1-1（AR移行）完了済みだが、階層化は導入せず現状維持。

---

## 10. 設定

### 10.1 hiveforge.config.yaml

```yaml
hive:
  name: "poc-project"
  vault_path: "./Vault"

governance:
  max_retries: 3              # タスクの最大リトライ回数
  max_oscillations: 5         # 状態振動検出閾値
  max_concurrent_tasks: 10    # 同時実行タスク数上限
  task_timeout_seconds: 300   # タスクタイムアウト（秒）
  heartbeat_interval_seconds: 30  # ハートビート間隔
  approval_timeout_hours: 24  # 承認待ちタイムアウト
  archive_after_days: 7       # アーカイブ日数

llm:
  provider: "openai"              # LiteLLM対応プロバイダー
  model: "gpt-4o"                 #   openai, anthropic, ollama, ollama_chat,
  api_key_env: "OPENAI_API_KEY"   #   groq, deepseek, litellm_proxy 等
  max_tokens: 4096
  temperature: 0.2
  # api_base: ""                  # Ollama/Proxy用カスタムエンドポイント
  # num_retries: 3                # LiteLLMリトライ回数
  # fallback_models: []           # フォールバック先

auth:
  enabled: false              # API認証（POCでは無効）
  api_key_env: "HIVEFORGE_API_KEY"

server:
  host: "0.0.0.0"
  port: 8000

logging:
  level: "INFO"
  events_max_file_size_mb: 100
```

### 10.2 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|------------|
| `HIVEFORGE_VAULT_PATH` | Vaultディレクトリパス | `./Vault` |
| `OPENAI_API_KEY` | OpenAI APIキー | - |
| `ANTHROPIC_API_KEY` | Anthropic APIキー（Anthropic使用時） | - |
| `HIVEFORGE_API_KEY` | HiveForge API認証キー | - |
| `LITELLM_PROXY_KEY` | LiteLLM Proxy認証キー（Proxy使用時） | - |

---

## 11. 開発計画・ゲート条件

### 11.1 概要

開発の進捗管理はフェーズベースからマイルストーンベースに移行しました。
詳細は [DEVELOPMENT_PLAN_v2.md](DEVELOPMENT_PLAN_v2.md) を参照してください。

### 11.2 マイルストーン

| マイルストーン | 目標 | ステータス |
|---------------|------|----------|
| M1: 基盤固め | AR移行、スタブ解消 | ✅ 完了（M1-1, M1-2） |
| M2: 接続 | Sentinel Hornet、VS Code↔API、エージェント間E2E | 🔄 M2-0/M2-1完了、M2-2/M2-3未着手 |
| M3: 適応的協調 | Honeycomb, Swarming, Guard Bee, Forager Bee, Referee Bee, Sentinel拡張, Waggle Dance, Scout Bee | ✅ 完了（M3-1〜M3-8全完了） |
| M4: 自律 | LLMタスク分解、Orchestrator | ✅ 完了（M4-1, M4-2） |
| M5: 運用品質 | セキュリティ、KPIダッシュボード、CI/CD | 🔄 M5-1/M5-3完了、M5-2/M5-4〜M5-6未着手 |

### 11.3 ゲート条件

以下は各マイルストーンの通過に必要な要件ゲートです:

| ID | 条件 | 検証方法 | 状態 |
|----|------|----------|------|
| G-01 | Colony間衝突検出が実装済み | `CONFLICT_DETECTED` イベント発行可能 | ✅ |
| G-02 | 衝突解決プロトコルが定義済み | `CONFLICT_RESOLVED` イベントとマージルール | ✅ |
| G-03 | 標準失敗理由の分類が完了 | `FailureReason` enum の使用 | ✅ |
| G-04 | タイムアウト検出が実装済み | `OPERATION_TIMEOUT` イベント発行 | ✅ |
| G-05 | Action Classが実装済み | `ActionClass`, `TrustLevel` による分類 | ✅ |
| G-06 | 確認要求マトリクスが定義済み | `requires_confirmation()` 関数 | ✅ |
| G-07 | Conference モードが動作 | `CONFERENCE_STARTED/ENDED` イベント | ✅ |
| G-08 | Hive/ColonyがAR永続化 | サーバー再起動後もデータ維持 | ✅ (M1-1) |
| G-09 | Beekeeperの全ハンドラが実装 | TODOスタブがゼロ | ✅ (M1-2) |
| G-10 | E2Eエージェントチェーンが動作 | Beekeeper→Queen→Worker完走 | M2 |
| G-11 | LLMタスク分解が動作 | 抽象目標→複数タスク自動分解 | ✅ (M4-1) |

---

## 12. 今後の拡張

### 12.1 主要な計画

- [x] Worker Bee: MCPサブプロセスベースのWorker
- [x] Queen Bee連携: タスク割り当て、進捗集約、リトライ
- [x] Colony優先度: 静的設定ベースのリソース配分
- [x] Honeycomb: 実行履歴・学習基盤 (M3-1) ✅
- [x] Swarming Protocol Engine: タスク適応的Colony編成 (M3-2) ✅
- [x] Guard Bee: Evidence-first品質検証 (M3-3) ✅
- [x] Forager Bee: 探索的テスト・影響分析「違和感検知」 (M3-4) ✅
- [x] Referee Bee: N案多面的採点・トーナメント選抜 (M3-5) ✅
- [x] Sentinel Hornet拡張: KPI劣化検出 + ロールバック/隔離 (M3-6) ✅
- [x] Waggle Dance: I/O構造化検証 (M3-7) ✅
- [x] Scout Bee: 過去実績に基づく編成最適化 (M3-8) ✅
- [x] Queen Bee タスク分解: LLMタスク分解実装 (M4-1) ✅
- [x] LLM Orchestrator: 自律的なタスク分解・実行 (M4-2) ✅
- [ ] Artifact管理: 成果物の保存と参照
- [ ] 因果リンクの自動設定（[Issue #001](issues/001-lineage-auto-parents.md)）
- [ ] イベント署名: 改ざん者の特定

### 12.2 VS Code拡張の拡充

- [x] Hive Monitor: リアルタイム活動可視化（Webview）
- [x] TreeView: Activity Hierarchy API連動
- [ ] 因果グラフ可視化（Webview）
- [ ] リアルタイムイベントストリーム

### 12.3 スケーラビリティ

- [ ] エンティティ別チェーン（並列書き込み対応）
- [ ] イベントアーカイブ
- [ ] 分散ストレージ対応

### 12.4 Plane分離アーキテクチャ（M5/M6構想）

サンドボックス実行環境により、エージェントの自動化と安全性を両立する。
詳細は [コンセプト_v6.md §9.4](コンセプト_v6.md) を参照。

- [ ] Step 1: docker compose 最小構成（Plane概念の導入）
- [ ] Step 2: Worker エフェメラルコンテナ化（Execution Plane分離）
- [ ] Step 3: Guard Bee / Sentinel Hornet 独立コンテナ化（Safety Plane分離）
- [ ] Step 4: git worktree 運用基盤（Colony × worktree） — 規約策定済み: [GIT_WORKFLOW.md](GIT_WORKFLOW.md)
- [ ] Step 5: 本番オーケストレーション（K8s / ECS）

**Action Class × コンテナ分離**:

| Action Class | 分離レベル |
|-------------|-----------|
| Read-only | 共有Runner + git worktree (read-only) |
| Reversible | スナップショット付きWorkspaceコンテナ |
| Irreversible | 専用隔離コンテナ + 人間承認必須 |

---

## 参照

- [DEVELOPMENT_PLAN_v2.md](DEVELOPMENT_PLAN_v2.md) - 開発計画（進捗の正）
- [v5-hive-design.md](design/v5-hive-design.md) - 詳細設計（Single Source of Truth）
- [QUICKSTART.md](QUICKSTART.md) - 動作確認手順
- [AGENTS.md](../AGENTS.md) - AI開発ガイドライン
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) - Gitワークフロー規約（ブランチ・Worktree・PRゲート）
- [コンセプト_v6.md](コンセプト_v6.md) - 設計思想（最新版）
