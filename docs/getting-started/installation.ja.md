# インストール

## 前提条件

- Python 3.11 以上
- VS Code（推奨）
- Docker（devcontainer用）

## Devcontainer（推奨）

付属のdevcontainerを使うのが最も簡単です。環境差異を排除し、再現可能なビルドを保証します。

1. VS Codeでプロジェクトを開く
2. コマンドパレット → **Dev Containers: Reopen in Container**

devcontainerには以下が含まれます：

- Python 3.12
- 全依存関係インストール済み（`pip install -e ".[dev]"`）
- 開発ツール：Ruff、pytest、mypy
- VS Code拡張機能：Python、Pylance、Ruff

## ローカルインストール

devcontainerを使用できない場合：

```bash
# 仮想環境の作成と有効化
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 開発用依存関係込みでインストール
pip install -e ".[dev]"
```

## GPUサポート（Windows + NVIDIA）

Rancher DesktopはGPUをサポートしていません。Ubuntu WSLのDockerを使用してください：

```powershell
# 1. Ubuntu WSLのDockerを起動
wsl -d Ubuntu -e sudo service docker start

# 2. GPUアクセステスト
wsl -d Ubuntu docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

または付属のスクリプトを使用：

```powershell
.\scripts\start-wsl-docker.cmd
```

## インストールの確認

```bash
# CLIが使えることを確認
hiveforge --help

# APIサーバーを起動
hiveforge server

# Swagger UIを開く
# http://localhost:8000/docs
```
