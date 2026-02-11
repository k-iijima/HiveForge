#!/usr/bin/env python3
"""VLM Tester の動作テストスクリプト（VLMなし版）

Playwrightで画面をキャプチャし、ローカル分析のみでテストします。
"""

import asyncio
from pathlib import Path


async def test_screen_capture():
    """画面キャプチャのテスト"""
    from playwright.async_api import async_playwright

    from colonyforge.vlm_tester import ScreenCapture

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


async def test_diff_analysis(image_data: bytes):
    """Diff分析のテスト"""
    import io

    from PIL import Image

    from colonyforge.vlm_tester import DiffAnalyzer

    print("\n" + "=" * 60)
    print("2. Diff分析テスト")
    print("=" * 60)

    diff = DiffAnalyzer()

    # 同一画像の比較
    result = await diff.compare(image_data, image_data)
    print("✓ 同一画像比較:")
    print(f"    is_same: {result.data['is_same']}")
    print(f"    diff_ratio: {result.data['diff_ratio']:.6f}")

    # 異なる画像との比較（色を変えた画像を作成）
    img = Image.open(io.BytesIO(image_data))
    # 赤色のオーバーレイを追加
    red_overlay = Image.new("RGB", img.size, (255, 0, 0))
    blended = Image.blend(img.convert("RGB"), red_overlay, 0.3)
    buffer = io.BytesIO()
    blended.save(buffer, format="PNG")
    modified_image = buffer.getvalue()

    result2 = await diff.compare(image_data, modified_image)
    print("✓ 異なる画像比較:")
    print(f"    is_same: {result2.data['is_same']}")
    print(f"    diff_ratio: {result2.data['diff_ratio']:.6f}")

    # 差分画像を保存
    diff_image = await diff.create_diff_image(image_data, modified_image)
    if diff_image:
        output_dir = Path("./test_captures")
        (output_dir / "diff_image.png").write_bytes(diff_image)
        print(f"✓ 差分画像保存: {output_dir / 'diff_image.png'}")


async def test_hybrid_analyzer(image_data: bytes):
    """HybridAnalyzer (LOCAL_ONLY) のテスト"""
    from colonyforge.vlm_tester import AnalysisLevel, HybridAnalyzer

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
    print(f"✓ ローカル結果キー: {list(result.local_results.keys())}")

    if "ocr" in result.local_results:
        ocr_result = result.local_results["ocr"]
        if ocr_result.success:
            text = ocr_result.data.get("text", "")[:200]
            print(f"✓ OCRテキスト: {text}...")
        else:
            print(f"  OCRエラー: {ocr_result.error}")

    print(f"✓ VLMレスポンス: {result.vlm_response}")

    stats = analyzer.get_stats()
    print(f"✓ 統計: {stats}")


async def test_action_executor():
    """ActionExecutorのテスト"""
    from playwright.async_api import async_playwright

    from colonyforge.vlm_tester import ActionExecutor, ScreenCapture

    print("\n" + "=" * 60)
    print("4. ActionExecutor テスト")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://example.com")
        print(f"✓ ページにアクセス: {page.url}")

        executor = ActionExecutor(mode="playwright")
        executor.set_page(page)

        capture = ScreenCapture(mode="playwright")
        capture.set_page(page)

        # 操作前のキャプチャ
        before = await capture.capture()
        Path("./test_captures/before_action.png").write_bytes(before)

        # クリック
        await executor.click(400, 300)
        print("✓ クリック実行 (400, 300)")

        # スクロール
        await executor.scroll(400, 300, delta_y=200)
        print("✓ スクロール実行 (delta_y=200)")

        # 操作後のキャプチャ
        after = await capture.capture()
        Path("./test_captures/after_action.png").write_bytes(after)
        print("✓ 操作前後のキャプチャ保存")

        # キー入力
        await executor.press_key("escape")
        print("✓ Escapeキー押下")

        await executor.press_key("ctrl+a")
        print("✓ Ctrl+A 押下")

        await browser.close()


async def test_mcp_server():
    """MCPサーバーの初期化テスト"""
    import tempfile

    from colonyforge.vlm_tester import VLMTesterMCPServer

    print("\n" + "=" * 60)
    print("5. VLMTesterMCPServer 初期化テスト")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        server = VLMTesterMCPServer(captures_dir=tmpdir)
        print(f"✓ サーバー名: {server.server.name}")
        print(f"✓ キャプチャディレクトリ: {server.captures_dir}")
        print("✓ MCPサーバー初期化完了")


async def main():
    """メインテスト"""
    print("\n🚀 VLM Tester 動作テスト（ローカル分析のみ）\n")

    # 1. 画面キャプチャ
    image_data = await test_screen_capture()

    # 2. Diff分析
    await test_diff_analysis(image_data)

    # 3. HybridAnalyzer
    await test_hybrid_analyzer(image_data)

    # 4. ActionExecutor
    await test_action_executor()

    # 5. MCPサーバー
    await test_mcp_server()

    print("\n" + "=" * 60)
    print("✅ テスト完了!")
    print("=" * 60)
    print("\n保存されたファイル:")
    for f in Path("./test_captures").glob("*.png"):
        print(f"  - {f}")


if __name__ == "__main__":
    asyncio.run(main())
