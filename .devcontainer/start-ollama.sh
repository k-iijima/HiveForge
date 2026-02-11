#!/bin/bash
# Ollama起動スクリプト（GPU自動検出）
# GPUがあればGPU版、なければCPU版を起動

set -e

cd /workspace/ColonyForge

# 既存のOllamaが動いているか確認
if curl -s http://ollama:11434/api/tags &>/dev/null || curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "✅ Ollama is already running, skipping startup..."
    exit 0
fi

# GPU検出（複数の方法を試行）
detect_gpu() {
    # 環境変数で明示的に指定されている場合
    if [ "$COLONYFORGE_GPU" = "nvidia" ]; then
        echo "  → COLONYFORGE_GPU=nvidia が設定されています"
        return 0
    fi

    # nvidia-smi が利用可能かチェック（Ubuntu WSL Docker の場合）
    if docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 true &>/dev/null 2>&1; then
        echo "  → docker --gpus オプションが利用可能"
        return 0
    fi

    # docker info で nvidia ランタイムを確認
    if docker info 2>/dev/null | grep -qi "nvidia"; then
        echo "  → docker info で nvidia ランタイムを検出"
        return 0
    fi

    echo "  → GPU未検出（COLONYFORGE_GPU=nvidia で強制可能）"
    return 1
}

if detect_gpu; then
    echo "🚀 GPU detected, starting Ollama with GPU support..."
    docker compose -f .devcontainer/docker-compose.dev.yml --profile gpu up -d ollama
else
    echo "💻 No GPU detected, starting Ollama in CPU mode..."
    docker compose -f .devcontainer/docker-compose.dev.yml --profile cpu up -d ollama-cpu
fi

# Ollamaの起動を待機
echo "⏳ Waiting for Ollama to be ready..."
for i in {1..30}; do
    if curl -s http://ollama:11434/api/tags &>/dev/null; then
        echo "✅ Ollama is ready!"
        exit 0
    fi
    sleep 1
done

echo "⚠️  Ollama may not be fully ready yet, but continuing..."
