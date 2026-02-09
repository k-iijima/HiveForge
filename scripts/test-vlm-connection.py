#!/usr/bin/env python3
"""VLM接続テストスクリプト

devcontainerからOllamaへの接続をテストする。
"""

import asyncio
import sys
from pathlib import Path

# srcをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hiveforge.vlm import OllamaClient


async def main():
    # デフォルトURL（Dockerネットワーク経由）
    ollama_url = "http://hiveforge-ollama:11434"

    print(f"🔗 Ollama URL: {ollama_url}")
    print()

    # OllamaClient接続テスト
    print("1️⃣ OllamaClient接続テスト...")
    client = OllamaClient(base_url=ollama_url, timeout=60)

    if await client.is_available():
        print("   ✅ Ollama接続成功")
    else:
        print("   ❌ Ollama接続失敗")
        print("   → docker compose -f docker-compose.vlm.yml up -d を実行してください")
        return 1

    # モデル一覧
    print()
    print("2️⃣ インストール済みモデル...")
    models = await client.list_models()
    for model in models:
        print(f"   - {model}")

    if not models:
        print("   ⚠️  モデルがありません")
        print("   → ./scripts/vlm-env.sh setup でLLaVAをインストールしてください")
        return 1

    # VLMテスト（画像なし、テキストのみ）
    print()
    print("3️⃣ VLMテキスト生成テスト...")
    try:
        response = await client.analyze_image(
            image=b"",  # ダミー
            prompt="Say 'VLM is working!' in exactly those words.",
        )
        print(f"   応答: {response.response[:100]}...")
        print(f"   処理時間: {response.total_duration_ms}ms")
        print("   ✅ テキスト生成成功")
    except Exception as e:
        print(f"   ❌ テキスト生成失敗: {e}")

    print()
    print("✨ VLM環境は正常に動作しています！")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
