# HiveForge

> 実験的・自律型ソフトウェア組立システム

HiveForgeは、LLMを活用した自律型ソフトウェア開発支援システムです。VS Code + GitHub Copilot Chat と連携し、要求の投入から実装・検証まで追跡可能なワークフローを提供します。

## 特徴

- **Akashic Record (AR)**: 全イベントを追記保存する不変ログ
- **因果追跡**: 任意の成果物から「なぜ」を遡及可能
- **状態機械**: Task/Run/Requirement の厳密な状態管理
- **MCP対応**: GitHub Copilot Chat から直接操作可能
- **VS Code統合**: 拡張機能でダッシュボード・イベントログ表示

## クイックスタート

### 前提条件

- Python 3.11以上
- VS Code + GitHub Copilot拡張機能（推奨）
- GitHub Copilotサブスクリプション

### 開発環境 (devcontainer推奨)

VS Codeのdevcontainerを使用すると、環境差異なく開発を開始できます。

```bash
# VS Codeでリポジトリを開く
code hiveforge

# コマンドパレット > "Dev Containers: Reopen in Container"
```

GPUの有無は自動検出されます：
- **GPU搭載**: NVIDIA GPU対応のOllamaが自動起動、VLM機能が利用可能
- **GPUなし**: CPU版Ollamaにフォールバック（低速だが動作）

### ローカルインストール

devcontainerを使用しない場合：

```bash
# リポジトリをクローン
git clone https://github.com/your-org/hiveforge.git
cd hiveforge

# 仮想環境を作成・有効化
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# 依存パッケージをインストール
pip install -e ".[dev]"

# 環境変数を設定
cp .env.example .env

# Vaultディレクトリを初期化
hiveforge init

# サーバーを起動
hiveforge serve
```

### VS Code MCP設定

`.vscode/settings.json` に追加:

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
User: @hiveforge システムの状態を教えて

User: @hiveforge 新しい要求を登録: Hello Worldアプリを作成
```

## プロジェクト構造

```
hiveforge/
├── src/hiveforge/
│   ├── core/           # コアロジック
│   │   ├── ar/         # Akashic Record
│   │   ├── state/      # 状態機械
│   │   └── orchestrator.py
│   ├── api/            # FastAPI エンドポイント
│   ├── mcp_server/     # MCP Server
│   └── cli.py          # CLIエントリポイント
├── tests/              # テスト
├── Vault/              # イベントログ・投影 (gitignore)
└── hiveforge.config.yaml
```

## ドキュメント

| ドキュメント | 説明 |
|--------------|------|
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 動作確認手順書 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | アーキテクチャ設計書 |
| [AGENTS.md](AGENTS.md) | AI開発ガイドライン |
| [コンセプト_v3.md](コンセプト_v3.md) | 完全な設計仕様 |

## 現在の実装状況

### POC必須成果物

- [x] VS CodeでCopilot Chat経由でHiveForgeと対話できる
- [x] VS Code拡張でダッシュボード・イベントログが確認できる
- [x] 要求を投入すると、AR（イベントログ）に記録される
- [x] タスクが生成・実行され、状態遷移が確認できる
- [x] 任意の成果物から「なぜ」を遡及できる（因果リンク）
- [x] 沈黙（タイムアウト）が検出され、記録・停止が発動する
- [x] 緊急停止（EmergencyStop）が機能する

### テスト状況

- **211テスト** 全てパス
- **カバレッジ 100%** 

## ライセンス

MIT License
