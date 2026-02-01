# HiveForge

> マルチエージェント協調開発システム

HiveForgeは、LLMを活用した自律型ソフトウェア開発支援システムです。複数の専門エージェント（Beekeeper, Queen Bee, Worker Bee）が協調し、VS Code + GitHub Copilot Chat と連携してソフトウェア開発を支援します。

## 特徴

- **マルチエージェント協調**: Beekeeper（調整役）、Queen Bee（Colony統括）、Worker Bee（実務）の階層構造
- **Hive/Colony階層**: 複数のRunを専門領域（Colony）で組織化
- **Akashic Record (AR)**: 全イベントを追記保存する不変ログ
- **因果追跡 (Lineage)**: 任意の成果物から「なぜ」を遡及可能
- **状態機械**: Hive/Colony/Run/Task/Requirement の厳密な状態管理
- **信頼レベル制御**: ActionClass × TrustLevel による承認制御
- **MCP対応**: GitHub Copilot Chat から直接操作可能
- **VS Code統合**: 拡張機能でダッシュボード・イベントログ表示

## 概念モデル

```
Hive（プロジェクト）
 │
 ├── Beekeeper（調整エージェント）
 │
 ├── Colony: UI/UX
 │    ├── Queen Bee（Colony統括）
 │    ├── Worker Bee: Designer
 │    ├── Worker Bee: A11y
 │    └── Run → Task...
 │
 ├── Colony: API
 │    ├── Queen Bee
 │    ├── Worker Bee: Backend
 │    └── Run → Task...
 │
 └── Colony: Infra
      ├── Queen Bee
      ├── Worker Bee: Docker
      └── Run → Task...
```

### 用語

| 用語 | 説明 |
|------|------|
| **Hive** | プロジェクト全体の環境 |
| **Beekeeper** | ユーザーとの対話窓口、Colony間調整 |
| **Colony** | 専門領域のエージェント群（UI/UX, API等） |
| **Queen Bee** | Colonyの統括エージェント |
| **Worker Bee** | 実務を行う専門エージェント |
| **Run** | 実行単位（タスクの集合） |
| **Task** | 個別の作業項目 |

## 実装状況

| フェーズ | 内容 | 状態 |
|---------|------|------|
| Phase 1 | Hive/Colony基盤、イベント、状態機械 | ✅ 完了 |
| Phase 2 | Worker Bee基盤、Queen Bee連携 | ✅ 完了 |
| Phase 3 | Beekeeper基盤、Escalation | ✅ 完了 |
| Phase 4 | 衝突検出・解決、Conference | ✅ 完了 |
| Phase 5 | ツール実行、リトライ、TrustLevel | ✅ 完了 |
| Phase 6+ | 統合テスト、UI強化 | 🔜 計画中 |

**テスト**: 1092 passed / カバレッジ 96%

詳細: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)

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

`.vscode/settings.json`:

```json
{
  "mcp": {
    "servers": {
      "hiveforge": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "hiveforge.mcp_server"],
        "cwd": "${workspaceFolder}",
        "env": {
          "HIVEFORGE_VAULT_PATH": "${workspaceFolder}/Vault"
        }
      }
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
├── api/               # REST API (FastAPI)
├── mcp_server/        # MCP Server
├── beekeeper/         # Beekeeper層
├── queen_bee/         # Queen Bee層
├── worker_bee/        # Worker Bee層
├── agent_ui/          # Agent UI MCPサーバー
├── vlm/               # VLM（画像解析）
├── vlm_tester/        # E2Eテスト支援
└── cli.py             # CLI

vscode-extension/      # VS Code拡張
tests/                 # テスト (1092件)
Vault/                 # イベントログ (gitignore)
```

## ドキュメント

| ドキュメント | 説明 |
|--------------|------|
| [AGENTS.md](AGENTS.md) | AI開発ガイドライン |
| [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | 実装状況サマリー |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | アーキテクチャ設計書 |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 動作確認手順書 |
| [docs/design/v5-hive-design.md](docs/design/v5-hive-design.md) | v5設計ドキュメント |

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
