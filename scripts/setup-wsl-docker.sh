#!/bin/bash
# ColonyForge Docker セットアップスクリプト
# Docker Desktop / WSL ネイティブ Docker の両方に対応
# GPU サポートの自動検出付き

set -e

echo "🐝 ColonyForge - Docker セットアップ (GPU対応)"
echo "============================================="

# ─── Docker 検出 ───────────────────────────────────────
detect_docker() {
    # 1. 既に docker が動いていればそれを使う（Docker Desktop 等）
    if docker info &>/dev/null 2>&1; then
        echo "docker-ready"
        return 0
    fi

    # 2. WSL ネイティブ Docker がインストールされている場合は起動を試みる
    if command -v dockerd &>/dev/null || [ -f /usr/bin/dockerd ]; then
        echo "wsl-native"
        return 0
    fi

    # 3. Docker が見つからない
    echo "not-found"
    return 0
}

DOCKER_MODE=$(detect_docker)

echo ""
case "$DOCKER_MODE" in
    docker-ready)
        DOCKER_HOST_INFO=$(docker info --format '{{.OperatingSystem}}' 2>/dev/null || echo "unknown")
        echo "✅ Docker は既に起動しています (${DOCKER_HOST_INFO})"
        ;;
    wsl-native)
        echo "🚀 WSL ネイティブ Docker を起動中..."
        sudo service docker start

        echo "⏳ Docker の起動を待機中..."
        for i in {1..30}; do
            if docker info &>/dev/null; then
                echo "✅ Docker が起動しました"
                break
            fi
            if [ "$i" -eq 30 ]; then
                echo "❌ Docker の起動がタイムアウトしました"
                exit 1
            fi
            sleep 1
        done
        ;;
    not-found)
        echo "❌ Docker が見つかりません"
        echo ""
        echo "以下のいずれかをインストールしてください："
        echo "  A) Docker Desktop for Windows（推奨）"
        echo "     https://www.docker.com/products/docker-desktop/"
        echo "     → 設定で 'Use the WSL 2 based engine' を有効に"
        echo ""
        echo "  B) WSL 内に Docker をネイティブインストール"
        echo "     sudo apt-get update && sudo apt-get install -y docker.io"
        echo "     sudo usermod -aG docker \$USER"
        exit 1
        ;;
esac

# ─── Docker コンテキスト情報 ──────────────────────────
echo ""
echo "📋 Docker 情報:"
echo "  バージョン: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'N/A')"
echo "  コンテキスト: $(docker context show 2>/dev/null || echo 'default')"
echo "  OS: $(docker info --format '{{.OperatingSystem}}' 2>/dev/null || echo 'N/A')"

# ─── GPU 確認 ─────────────────────────────────────────
echo ""
echo "🎮 GPU 確認:"
GPU_AVAILABLE=false

if nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    echo ""
    echo "🧪 Docker GPU テスト:"
    if docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null; then
        echo "✅ Docker から GPU にアクセス可能"
        GPU_AVAILABLE=true
    else
        echo "⚠️  Docker から GPU にアクセスできません（CPU モードで動作します）"
    fi
else
    echo "  GPU が検出されませんでした（CPU モードで動作します）"
fi

# ─── 使い方 ───────────────────────────────────────────
echo ""
echo "📝 使い方:"
echo "  1. VS Code で 'Dev Containers: Reopen in Container' を実行"
if [ "$GPU_AVAILABLE" = true ]; then
    echo "  2. または: docker compose -f .devcontainer/docker-compose.dev.yml --profile gpu up -d"
else
    echo "  2. または: docker compose -f .devcontainer/docker-compose.dev.yml --profile cpu up -d"
fi
echo ""
