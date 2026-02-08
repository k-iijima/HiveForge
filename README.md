# HiveForge

[![CI](https://github.com/k-iijima/HiveForge/actions/workflows/ci.yml/badge.svg)](https://github.com/k-iijima/HiveForge/actions/workflows/ci.yml)

> マルチエージェント協調開発システム

HiveForgeは、LLMを活用した自律型ソフトウェア開発支援システムです。複数の専門エージェント（Beekeeper, Queen Bee, Worker Bee, Sentinel Hornet, Guard Bee, Forager Bee, Referee Bee）が協調し、VS Code + GitHub Copilot Chat と連携してソフトウェア開発を支援します。

## 特徴

- **マルチエージェント協調**: Beekeeper（Hive統括）、Queen Bee（Colony統括）、Worker Bee（実務）、Sentinel Hornet（監視・執行）、Guard Bee（品質検証）、Forager Bee（探索的テスト）、Referee Bee（多面的採点・選抜）の階層構造
- **大量生成→自動検証→生存選抜**: 「1回で正解を出す」から「N案並列生成 + 厳密な自動審判」へのパラダイムシフト
- **Hive/Colony階層**: 複数のRunを専門領域（Colony）で組織化
- **Swarming Protocol**: タスク特性に応じた適応的Colony編成
- **Akashic Record (AR)**: 全イベントを追記保存する不変ログ
- **Honeycomb**: 実行履歴からの学習・改善基盤
- **因果追跡 (Lineage)**: 任意の成果物から「なぜ」を遡及可能
- **状態機械**: Hive/Colony/Run/Task/Requirement の厳密な状態管理
- **信頼レベル制御**: ActionClass × TrustLevel による承認制御
- **Evidence-first**: 証拠に基づく判断原則（diff, テスト結果, 根拠）
- **MCP対応**: GitHub Copilot Chat から直接操作可能
- **VS Code統合**: 拡張機能でダッシュボード・イベントログ表示

## 概念モデル

```
Hive（プロジェクト）
 │
 ├── Beekeeper（調整エージェント）─── Swarming Protocol（適応的Colony編成）
 │
 ├── Sentinel Hornet（監視・異常検出・強制停止）
 │
 ├── Colony: UI/UX
 │    ├── Queen Bee（Colony統括）
 │    ├── Worker Bee: Designer × N案並列
 │    └── Run → Task...
 │
 ├── Colony: API
 │    ├── Queen Bee
 │    ├── Worker Bee: Backend × N案並列
 │    └── Run → Task...
 │
 ├── Forager Bee（探索的テスト・影響分析）
 ├── Referee Bee（多面的採点・自動選抜）
 ├── Guard Bee（最終品質ゲート）
 │
 └── Honeycomb（実行履歴・学習）+ Scout Bee（編成最適化）
```

### パイプライン（大量生成→選抜）

```
Worker × N案生成 → Forager探索拡張 → Referee多面的採点 → Guard最終ゲート → Sentinel本番監視
```

### 用語

| 用語 | 説明 |
|------|------|
| **Hive** | プロジェクト全体の環境 |
| **Beekeeper** | ユーザーとの対話窓口、複数Hive統括 |
| **Colony** | 専門領域のエージェント群（UI/UX, API等） |
| **Queen Bee** | Colonyの統括エージェント |
| **Worker Bee** | 実務を行う専門エージェント（N案並列生成可） |
| **Sentinel Hornet** | Hive内監視・異常検出・強制停止の一体型エージェント |
| **Guard Bee** | 最終品質ゲート（PASS/CONDITIONAL_PASS/FAIL） |
| **Forager Bee** | 探索的テスト・変更影響分析・違和感検知 |
| **Referee Bee** | N案の多面的自動採点・生存選抜（トーナメント） |
| **Scout Bee** | 過去実績に基づくColony編成最適化 |
| **Swarming Protocol** | タスク適応的Colony編成プロトコル |
| **Honeycomb** | 実行履歴からの学習基盤 |
| **Waggle Dance** | エージェント間の構造化通信プロトコル |
| **Run** | 実行単位（タスクの集合） |
| **Task** | 個別の作業項目 |

## 開発ステータス

**M4（自律的タスク分解）完了** — LLMタスク分解（TaskPlanner）、並列実行（ColonyOrchestrator）、ゲート統合（ExecutionPipeline）が実装済。次はM5（運用品質）およびM2-2/M2-3（エージェント間E2E統合）。

| マイルストーン | 状態 |
|--|–|
| M1: 基盤固め | ✅ 完了 |
| M2: 接続 | M2-0/M2-1 完了、M2-2/M2-3 未着手 |
| M3: 適応的協調 | ✅ 全完了 (M3-1〜M3-8) |
| M4: 自律 | ✅ 完了 (M4-1, M4-2) |
| M5: 運用品質 | ★次に着手 |

詳細: [docs/DEVELOPMENT_PLAN_v2.md](docs/DEVELOPMENT_PLAN_v2.md)

テスト実行: `pytest tests --ignore=tests/e2e -q`

## クイックスタート

### 開発環境 (devcontainer推奨)

```bash
# VS Codeでリポジトリを開く
code hiveforge

# コマンドパレット > "Dev Containers: Reopen in Container"
```

GPUの有無は自動検出：
- **GPU搭載**: NVIDIA GPU対応のOllamaが自動起動、VLM機能が利用可能
- **GPUなし**: CPU版Ollamaにフォールバック

### ローカルインストール

```bash
# リポジトリをクローン
git clone https://github.com/your-org/hiveforge.git
cd hiveforge

# 仮想環境を作成・有効化
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 依存パッケージをインストール
pip install -e ".[dev]"

# Vaultディレクトリを初期化
hiveforge init

# サーバーを起動
hiveforge serve
```

### VS Code MCP設定

`.vscode/mcp.json`:

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

### Copilot Chatで使用

```
@hiveforge システムの状態を教えて
@hiveforge 新しいHiveを作成: ECサイト開発
@hiveforge UI/UX Colonyを作成
```

## プロジェクト構造

```
src/hiveforge/
├── core/              # コア基盤（イベント、AR、状態機械）
│   ├── events/        #   84 EventType (パッケージ化済)
│   ├── ar/            #   Akashic Record (JSONL永続化)
│   ├── state/         #   5状態機械
│   ├── honeycomb/     #   実行履歴・学習基盤 (M3-1)
│   └── swarming/      #   Swarming Protocol (M3-2)
├── api/               # REST API (FastAPI)
├── mcp_server/        # MCP Server
├── beekeeper/         # Beekeeper層
├── sentinel_hornet/   # Sentinel Hornet（7パターン+KPI劣化+ロールバック/隔離）
├── queen_bee/         # Queen Bee層
├── worker_bee/        # Worker Bee層
├── guard_bee/         # Guard Bee（Evidence-first品質検証, M3-3）
├── forager_bee/       # Forager Bee（探索的テスト・影響分析, M3-4）
├── referee_bee/       # Referee Bee（多面的採点・選抜, M3-5）
├── scout_bee/         # Scout Bee（編成最適化, M3-8）
├── waggle_dance/      # Waggle Dance（I/O検証, M3-7）
├── llm/               # LLM統合（AgentRunner, プロンプト管理）
├── agent_ui/          # Agent UI MCPサーバー
├── vlm/               # VLM（画像解析）
├── vlm_tester/        # E2Eテスト支援
├── silence.py         # 沈黙検出
└── cli.py             # CLI

vscode-extension/      # VS Code拡張
tests/                 # テスト
Vault/                 # イベントログ (gitignore)
```

## ドキュメント

| ドキュメント | 役割 | 説明 |
|--------------|------|------|
| [AGENTS.md](AGENTS.md) | 規約 | AI開発ガイドライン |
| [docs/コンセプト_v6.md](docs/コンセプト_v6.md) | **なぜ** | 設計思想・ビジョン・ユースケース |
| [docs/design/v5-hive-design.md](docs/design/v5-hive-design.md) | **何を** | 詳細設計・スキーマ・プロトコル（Single Source of Truth） |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **今どうなっている** | 実装の現況・コンポーネント構成 |
| [docs/DEVELOPMENT_PLAN_v2.md](docs/DEVELOPMENT_PLAN_v2.md) | **次に何をする** | 開発計画・マイルストーン |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 手順 | 動作確認手順書 |

> ドキュメント間の不整合を防ぐため、各情報に**正規の記載場所**を定めています。
> 状態機械・イベント型・プロトコルの定義は v5-hive-design.md を正とし、他のドキュメントは参照リンクで接続します。

## テスト実行

```bash
# ユニットテスト
pytest tests/ --ignore=tests/e2e -v

# E2Eテスト（VLM使用）
pytest tests/e2e/ -v -m e2e

# カバレッジ
pytest --cov=hiveforge --cov-report=html
```

## ライセンス

MIT License
