#!/usr/bin/env python3
"""Agent UI MCP Server の動作テスト

実際にブラウザを操作して動作を確認します。
"""

import asyncio
import os

# Ollama URL設定
os.environ["OLLAMA_BASE_URL"] = "http://hiveforge-dev-ollama:11434"


async def main():
    from hiveforge.agent_ui.server import AgentUIMCPServer

    print("\n🚀 Agent UI MCP Server 動作テスト\n")

    server = AgentUIMCPServer(captures_dir="./agent_captures")

    # 1. ナビゲート
    print("=" * 60)
    print("1. navigate: example.com に移動")
    print("=" * 60)
    result = await server._handle_navigate({"url": "https://example.com"})
    print(f"   {result[0].text}")

    # 2. キャプチャ
    print("\n" + "=" * 60)
    print("2. capture_screen: 画面をキャプチャ")
    print("=" * 60)
    result = await server._handle_capture_screen({"save": True})
    for r in result:
        if hasattr(r, "text"):
            print(f"   {r.text}")
        elif hasattr(r, "mimeType"):
            print(f"   画像データ: {r.mimeType}, {len(r.data)} bytes (base64)")

    # 3. ページ説明
    print("\n" + "=" * 60)
    print("3. describe_page: ページを説明（VLM分析）")
    print("=" * 60)
    result = await server._handle_describe_page({"focus": "タイトル"})
    for r in result:
        if hasattr(r, "text"):
            print(f"   {r.text[:200]}..." if len(r.text) > 200 else f"   {r.text}")

    # 4. クリック
    print("\n" + "=" * 60)
    print("4. click: 座標 (400, 200) をクリック")
    print("=" * 60)
    result = await server._handle_click({"x": 400, "y": 200})
    print(f"   {result[0].text}")

    # 5. スクロール
    print("\n" + "=" * 60)
    print("5. scroll: 下にスクロール")
    print("=" * 60)
    result = await server._handle_scroll({"direction": "down", "amount": 200})
    print(f"   {result[0].text}")

    # 6. 比較
    print("\n" + "=" * 60)
    print("6. compare_with_previous: 前回と比較")
    print("=" * 60)
    # もう一度キャプチャして比較
    await server._handle_capture_screen({"save": False})
    result = await server._handle_compare({})
    for r in result:
        if hasattr(r, "text"):
            print(f"   {r.text}")

    # 7. キー入力
    print("\n" + "=" * 60)
    print("7. press_key: Ctrl+A")
    print("=" * 60)
    result = await server._handle_press_key({"key": "ctrl+a"})
    print(f"   {result[0].text}")

    # 8. 履歴一覧
    print("\n" + "=" * 60)
    print("8. list_captures: キャプチャ履歴")
    print("=" * 60)
    result = await server._handle_list_captures({"limit": 5})
    print(f"   {result[0].text}")

    # 9. ブラウザ閉じる
    print("\n" + "=" * 60)
    print("9. close_browser: ブラウザを閉じる")
    print("=" * 60)
    result = await server._handle_close_browser({})
    print(f"   {result[0].text}")

    print("\n" + "=" * 60)
    print("✅ テスト完了!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
