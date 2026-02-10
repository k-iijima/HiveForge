#!/usr/bin/env python3
"""VLM Tester の動作テストスクリプト

Playwrightで画面をキャプチャし、VLMで分析するシナリオをテストします。
"""

import asyncio
import os
from pathlib import Path

# Ollama URLを設定（Docker内）
os.environ["OLLAMA_BASE_URL"] = "http://hiveforge-dev-ollama:11434"


async def test_screen_capture():
    """画面キャプチャのテスト"""
    from playwright.async_api import async_playwright

    from hiveforge.vlm_tester import ScreenCapture

    print("=" * 60)
    print("1. Playwright + ScreenCapture テスト")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # サンプルページにアクセス
        await page.goto("https://example.com")
        print(f"✓ ページにアクセス: {page.url}")

        # ScreenCaptureでキャプチャ
        capture = ScreenCapture(mode="playwright")
        capture.set_page(page)

        image_data = await capture.capture()
        print(f"✓ キャプチャ取得: {len(image_data)} bytes")

        # 保存
        output_dir = Path("./test_captures")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "example_com.png"
        output_path.write_bytes(image_data)
        print(f"✓ 保存: {output_path}")

        await browser.close()

    return image_data


async def test_local_analysis(image_data: bytes):
    """ローカル分析のテスト（OCR/Diff）"""
    from hiveforge.vlm_tester import AnalysisLevel, DiffAnalyzer, HybridAnalyzer

    print("\n" + "=" * 60)
    print("2. ローカル分析テスト（Diff）")
    print("=" * 60)

    # 同一画像の比較
    diff = DiffAnalyzer()
    result = await diff.compare(image_data, image_data)
    print(
        f"✓ 同一画像比較: is_same={result.data['is_same']}, diff_ratio={result.data['diff_ratio']:.4f}"
    )

    # HybridAnalyzer（LOCAL_ONLYモード）
    print("\n" + "=" * 60)
    print("3. HybridAnalyzer (LOCAL_ONLY) テスト")
    print("=" * 60)

    analyzer = HybridAnalyzer()
    result = await analyzer.analyze(
        image_data,
        "この画面を説明してください",
        level=AnalysisLevel.LOCAL_ONLY,
    )
    print(f"✓ 分析レベル: {result.analysis_level.value}")
    print(f"✓ ローカル結果: {list(result.local_results.keys())}")
    print(f"✓ VLMレスポンス: {result.vlm_response}")


async def test_vlm_providers():
    """VLMプロバイダーの確認"""
    from hiveforge.vlm_tester import AnthropicProvider, MultiProviderVLMClient, OllamaProvider

    print("\n" + "=" * 60)
    print("4. VLMプロバイダー状態確認")
    print("=" * 60)

    ollama = OllamaProvider(base_url="http://hiveforge-dev-ollama:11434")
    print(f"  Ollama available: {ollama.is_available()}")

    anthropic = AnthropicProvider()
    print(f"  Anthropic available: {anthropic.is_available()}")

    client = MultiProviderVLMClient()
    available = client.get_available_providers()
    print(f"  利用可能なプロバイダー: {available}")


async def test_ollama_vlm(image_data: bytes):
    """Ollama VLMでの分析テスト"""
    from hiveforge.vlm_tester import OllamaProvider

    print("\n" + "=" * 60)
    print("5. Ollama VLM 分析テスト")
    print("=" * 60)

    provider = OllamaProvider(base_url="http://hiveforge-dev-ollama:11434")

    if not provider.is_available():
        print("⚠ Ollamaが利用できません")
        return

    # モデルがあるか確認
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get("http://hiveforge-dev-ollama:11434/api/tags")
        models = response.json().get("models", [])
        model_names = [m["name"] for m in models]
        print(f"  利用可能なモデル: {model_names}")

        if not any("llava" in m for m in model_names):
            print("⚠ llavaモデルがありません。ダウンロード中かもしれません。")
            print("  以下のコマンドでダウンロードできます:")
            print('  curl http://hiveforge-dev-ollama:11434/api/pull -d \'{"name": "llava:7b"}\'')
            return

    print("  VLM分析を実行中...")
    try:
        result = await provider.analyze(image_data, "この画面を日本語で説明してください")
        print(f"✓ VLMレスポンス:\n{result.response[:500]}...")
    except Exception as e:
        print(f"✗ エラー: {e}")


async def test_action_executor():
    """ActionExecutorのテスト"""
    from playwright.async_api import async_playwright

    from hiveforge.vlm_tester import ActionExecutor

    print("\n" + "=" * 60)
    print("6. ActionExecutor テスト")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://example.com")

        executor = ActionExecutor(mode="playwright")
        executor.set_page(page)

        # クリック
        await executor.click(100, 100)
        print("✓ クリック実行")

        # スクロール
        await executor.scroll(100, 100, delta_y=200)
        print("✓ スクロール実行")

        # キー入力
        await executor.press_key("escape")
        print("✓ Escapeキー押下")

        await browser.close()


async def main():
    """メインテスト"""
    print("\n🚀 VLM Tester 動作テスト\n")

    # 1. 画面キャプチャ
    image_data = await test_screen_capture()

    # 2. ローカル分析
    await test_local_analysis(image_data)

    # 3. VLMプロバイダー確認
    await test_vlm_providers()

    # 4. Ollama VLM分析
    await test_ollama_vlm(image_data)

    # 5. ActionExecutor
    await test_action_executor()

    print("\n" + "=" * 60)
    print("✅ テスト完了!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
