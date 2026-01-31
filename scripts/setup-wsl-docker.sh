#!/bin/bash
# Ubuntu WSL Docker セットアップスクリプト
# GPU サポート付きで Docker を起動します

set -e

echo "🐝 HiveForge - Ubuntu WSL Docker (GPU対応)"
echo "============================================"

# Docker サービスを起動
echo "🚀 Docker を起動中..."
sudo service docker start

# Docker が起動するのを待機
echo "⏳ Docker の起動を待機中..."
for i in {1..30}; do
    if docker info &>/dev/null; then
        echo "✅ Docker が起動しました"
        break
    fi
    sleep 1
done

# GPU の確認
echo ""
echo "🎮 GPU 確認:"
if nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    echo ""
    echo "🧪 Docker GPU テスト:"
    docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null && echo "✅ Docker から GPU にアクセス可能" || echo "❌ Docker から GPU にアクセスできません"
else
    echo "❌ GPU が検出されませんでした"
fi

echo ""
echo "📝 使い方:"
echo "  1. VS Code で 'Dev Containers: Reopen in Container' を実行"
echo "  2. または: docker compose -f .devcontainer/docker-compose.dev.yml --profile gpu up -d"
echo ""
