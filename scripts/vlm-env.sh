#!/bin/bash
# ColonyForge VLMテスト環境管理スクリプト
# Ollama（ローカルVLM）+ code-server（テスト対象）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# sudoが必要かどうかを判定
DOCKER_CMD="docker"
if ! docker ps >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
fi

COMPOSE_CMD="$DOCKER_CMD compose"

# GPU検出関数
detect_gpu() {
    # NVIDIA GPUが利用可能かチェック
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        echo "nvidia"
        return 0
    fi
    
    # Docker内からホストのGPUをチェック
    if $DOCKER_CMD run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi &>/dev/null 2>&1; then
        echo "nvidia"
        return 0
    fi
    
    echo "cpu"
    return 0
}

# GPU検出（環境変数で上書き可能）
GPU_TYPE="${COLONYFORGE_GPU:-$(detect_gpu)}"

# Composeファイル選択
if [ "$GPU_TYPE" = "nvidia" ]; then
    COMPOSE_FILE="docker-compose.vlm-gpu.yml"
    GPU_LABEL="🎮 GPU (NVIDIA)"
else
    COMPOSE_FILE="docker-compose.vlm.yml"
    GPU_LABEL="💻 CPU"
fi

echo "🐝 ColonyForge VLM Environment"
echo "============================="
echo "   Mode: $GPU_LABEL"
echo ""

ACTION="${1:-help}"

case "$ACTION" in
    setup)
        echo "📦 VLM環境をセットアップ中..."
        $COMPOSE_CMD -f $COMPOSE_FILE up -d
        
        echo ""
        echo "🦙 LLaVAモデルをダウンロード中（初回のみ数分かかります）..."
        sleep 5
        $DOCKER_CMD exec colonyforge-ollama ollama pull llava:7b
        
        echo ""
        echo "✅ セットアップ完了!"
        echo ""
        echo "使い方:"
        echo "  code-server: http://localhost:8080 (パスワード: colonyforge)"
        echo "  Ollama API:  http://localhost:11434"
        echo ""
        echo "Pythonから使用:"
        echo "  from colonyforge.vlm import LocalVLMAnalyzer"
        echo "  analyzer = LocalVLMAnalyzer()"
        echo "  result = await analyzer.analyze('screenshot.png')"
        ;;
        
    start)
        echo "🚀 VLM環境を起動中..."
        $COMPOSE_CMD -f $COMPOSE_FILE up -d
        echo ""
        echo "✅ 起動完了!"
        echo "  code-server: http://localhost:8080"
        echo "  Ollama API:  http://localhost:11434"
        ;;
        
    stop)
        echo "🛑 VLM環境を停止中..."
        $COMPOSE_CMD -f $COMPOSE_FILE down
        echo "✅ 停止完了"
        ;;
        
    status)
        echo "📊 コンテナ状態:"
        $DOCKER_CMD ps --filter "name=colonyforge-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        
        echo ""
        echo "🦙 Ollamaモデル:"
        $DOCKER_CMD exec colonyforge-ollama ollama list 2>/dev/null || echo "  (Ollamaが起動していません)"
        
        echo ""
        echo "🎮 GPU状態:"
        if [ "$GPU_TYPE" = "nvidia" ]; then
            $DOCKER_CMD exec colonyforge-ollama nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader 2>/dev/null || echo "  GPU情報を取得できません"
        else
            echo "  CPUモードで動作中"
        fi
        ;;
        
    test)
        echo "🧪 VLM解析テストを実行中..."
        python -c "
import asyncio
from colonyforge.vlm import LocalVLMAnalyzer

async def test():
    analyzer = LocalVLMAnalyzer()
    
    # 接続確認
    if not await analyzer.is_ready():
        print('❌ VLM環境が準備できていません')
        print('   ./scripts/vlm-env.sh setup を実行してください')
        return
    
    print('✅ VLM環境OK')
    print(f'   Model: {analyzer.client.model}')
    
    # サンプル解析（テスト用の小さい画像を生成）
    from PIL import Image
    import io
    img = Image.new('RGB', (100, 100), color='blue')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    
    print('📸 テスト画像を解析中...')
    result = await analyzer.analyze(buf.getvalue(), 'What color is this image?')
    print(f'✅ 解析完了 ({result.duration_ms}ms)')
    print(f'   結果: {result.analysis[:100]}...')

asyncio.run(test())
"
        ;;
        
    logs)
        $COMPOSE_CMD -f $COMPOSE_FILE logs -f
        ;;
        
    shell)
        echo "🐚 Ollamaコンテナに接続中..."
        $DOCKER_CMD exec -it colonyforge-ollama bash
        ;;
        
    clean)
        echo "🧹 環境をクリーンアップ中..."
        $COMPOSE_CMD -f $COMPOSE_FILE down -v
        echo "✅ クリーンアップ完了"
        ;;
        
    help|*)
        echo ""
        echo "使い方: $0 <command>"
        echo ""
        echo "コマンド:"
        echo "  setup   - 環境をセットアップ（初回のみ）"
        echo "  start   - コンテナを起動"
        echo "  stop    - コンテナを停止"
        echo "  status  - コンテナ状態を確認"
        echo "  test    - VLM解析テストを実行"
        echo "  logs    - ログを表示"
        echo "  shell   - Ollamaコンテナにシェル接続"
        echo "  clean   - 環境を完全削除"
        echo ""
        echo "GPU設定:"
        echo "  自動検出: NVIDIA GPUがあれば自動的に使用"
        echo "  強制CPU: COLONYFORGE_GPU=cpu $0 start"
        echo "  強制GPU: COLONYFORGE_GPU=nvidia $0 start"
        echo ""
        echo "アーキテクチャ:"
        echo "  ┌─────────────────────┐"
        echo "  │  Playwright MCP     │ ← 公式（スクショ取得）"
        echo "  │  @playwright/mcp    │"
        echo "  └──────────┬──────────┘"
        echo "             │ screenshot.png"
        echo "  ┌──────────▼──────────┐"
        echo "  │  LocalVLMAnalyzer   │ ← ColonyForge（解析）"
        echo "  │  (colonyforge.vlm)    │"
        echo "  └──────────┬──────────┘"
        echo "             │"
        echo "  ┌──────────▼──────────┐"
        echo "  │  Ollama (LLaVA)     │ ← ローカルVLM ($GPU_LABEL)"
        echo "  │  localhost:11434    │"
        echo "  └─────────────────────┘"
        echo ""
        ;;
esac
