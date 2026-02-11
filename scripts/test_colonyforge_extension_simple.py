#!/usr/bin/env python3
"""ColonyForge拡張テストのシンプル実行スクリプト

使い方:
    # code-serverを使う場合
    python scripts/test_colonyforge_extension_simple.py --url http://localhost:8080

    # ローカルファイルでテスト（テスト用HTMLページ）
    python scripts/test_colonyforge_extension_simple.py --demo
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ["OLLAMA_BASE_URL"] = os.environ.get(
    "OLLAMA_BASE_URL", "http://colonyforge-dev-ollama:11434"
)
os.environ["VLM_HEADLESS"] = "false"  # テスト時はブラウザを見せる


async def create_demo_page():
    """テスト用のデモHTMLページを作成"""
    demo_html = Path(__file__).parent / "colonyforge_demo.html"
    demo_html.write_text("""<!DOCTYPE html>
<html>
<head>
    <title>ColonyForge Dashboard Demo</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #1e1e1e; 
            color: #cccccc; 
            margin: 0; 
            padding: 0;
        }
        .container { display: flex; height: 100vh; }
        .activity-bar {
            width: 48px; 
            background: #333333;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding-top: 10px;
        }
        .activity-icon {
            width: 24px;
            height: 24px;
            margin: 8px;
            cursor: pointer;
            opacity: 0.6;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
        }
        .activity-icon:hover, .activity-icon.active { opacity: 1; }
        .sidebar {
            width: 260px;
            background: #252526;
            border-right: 1px solid #3c3c3c;
        }
        .sidebar-header {
            padding: 10px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #bbbbbb;
        }
        .view-section {
            border-bottom: 1px solid #3c3c3c;
        }
        .view-title {
            padding: 8px 10px;
            font-size: 11px;
            font-weight: 600;
            background: #2d2d2d;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .view-title:hover { background: #37373d; }
        .view-content { padding: 8px 10px; }
        .item {
            padding: 4px 8px;
            margin: 2px 0;
            border-radius: 3px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .item:hover { background: #2a2d2e; }
        .badge {
            background: #007acc;
            color: white;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 10px;
        }
        .main-content {
            flex: 1;
            padding: 20px;
        }
        .dashboard-title {
            font-size: 24px;
            margin-bottom: 20px;
        }
        .status-icon { font-size: 14px; }
        .running { color: #73c991; }
        .pending { color: #e2c08d; }
        .completed { color: #4ec9b0; }
        .btn {
            background: #0e639c;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }
        .btn:hover { background: #1177bb; }
        .btn-approve { background: #388a34; }
        .btn-reject { background: #a31515; }
    </style>
</head>
<body>
    <div class="container">
        <div class="activity-bar">
            <div class="activity-icon" title="Explorer">📁</div>
            <div class="activity-icon" title="Search">🔍</div>
            <div class="activity-icon" title="Source Control">📊</div>
            <div class="activity-icon active" title="ColonyForge">🐝</div>
            <div class="activity-icon" title="Extensions">🧩</div>
        </div>
        <div class="sidebar">
            <div class="sidebar-header">ColonyForge</div>
            
            <div class="view-section">
                <div class="view-title">
                    <span>▼ RUNS</span>
                    <span class="badge">3</span>
                </div>
                <div class="view-content">
                    <div class="item"><span class="status-icon running">●</span> Run-001 (実行中)</div>
                    <div class="item"><span class="status-icon pending">●</span> Run-002 (待機中)</div>
                    <div class="item"><span class="status-icon completed">●</span> Run-003 (完了)</div>
                </div>
            </div>
            
            <div class="view-section">
                <div class="view-title">
                    <span>▼ TASKS</span>
                    <span class="badge">5</span>
                </div>
                <div class="view-content">
                    <div class="item"><span class="status-icon running">●</span> Task-001: ログイン機能実装</div>
                    <div class="item"><span class="status-icon pending">●</span> Task-002: UIデザイン</div>
                    <div class="item"><span class="status-icon running">●</span> Task-003: API設計</div>
                    <div class="item"><span class="status-icon completed">●</span> Task-004: テスト作成</div>
                    <div class="item"><span class="status-icon pending">●</span> Task-005: ドキュメント</div>
                </div>
            </div>
            
            <div class="view-section">
                <div class="view-title">
                    <span>▼ 確認要請</span>
                    <span class="badge">2</span>
                </div>
                <div class="view-content">
                    <div class="item">
                        <span>⚠️ デザイン変更の確認</span>
                        <button class="btn btn-approve">承認</button>
                        <button class="btn btn-reject">却下</button>
                    </div>
                    <div class="item">
                        <span>⚠️ APIエンドポイント追加</span>
                        <button class="btn btn-approve">承認</button>
                        <button class="btn btn-reject">却下</button>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            <h1 class="dashboard-title">🐝 ColonyForge Dashboard</h1>
            <p>Welcome to ColonyForge - AI-Powered Development Orchestration</p>
            
            <h2>Active Run: Run-001</h2>
            <p>Status: <span class="running">●</span> Running</p>
            <p>Tasks: 3/5 completed</p>
            <p>Requirements: 2 pending approval</p>
            
            <div style="margin-top: 20px;">
                <button class="btn">New Run</button>
                <button class="btn">View Events</button>
            </div>
        </div>
    </div>
</body>
</html>
""")
    return f"file://{demo_html.absolute()}"


async def run_test(url: str, headless: bool = False):
    """テストを実行"""
    from colonyforge.agent_ui.server import AgentUIMCPServer

    if headless:
        os.environ["VLM_HEADLESS"] = "true"
    else:
        os.environ["VLM_HEADLESS"] = "false"

    print("\n" + "=" * 60)
    print("🐝 ColonyForge Extension Visual Test")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Headless: {headless}")

    server = AgentUIMCPServer(captures_dir="./test_captures")

    # ステップ 1: ページを開く
    print("\n📍 Step 1: Open ColonyForge Dashboard")
    result = await server._handle_navigate({"url": url})
    print(f"   {result[0].text}")
    await asyncio.sleep(2)

    # ステップ 2: 画面をキャプチャ
    print("\n📸 Step 2: Capture Screen")
    capture_result = await server._handle_capture_screen({"save": True})
    for r in capture_result:
        if hasattr(r, "text"):
            print(f"   {r.text}")

    # ステップ 3: VLMで分析
    print("\n🤖 Step 3: Analyze with VLM")
    describe_result = await server._handle_describe_page(
        {
            "focus": "Describe the ColonyForge dashboard. What views are visible? (Runs, Tasks, Requirements)"
        }
    )
    for r in describe_result:
        if hasattr(r, "text"):
            print(f"   VLM: {r.text[:500]}...")

    # ステップ 4: 要素を探す
    print("\n🔍 Step 4: Find ColonyForge Icon")
    find_result = await server._handle_find_element(
        {"description": "ColonyForge icon (bee icon 🐝) in the activity bar"}
    )
    for r in find_result:
        if hasattr(r, "text"):
            print(f"   {r.text[:300]}")

    # ステップ 5: Runsセクションをクリック
    print("\n🖱️ Step 5: Click on Runs section")
    await server._handle_click({"element": "RUNS section header"})
    await asyncio.sleep(0.5)

    # ステップ 6: 再度キャプチャ
    print("\n📸 Step 6: Capture after click")
    await server._handle_capture_screen({"save": True})

    # ステップ 7: 差分分析
    print("\n📊 Step 7: Compare with previous")
    compare_result = await server._handle_compare({})
    for r in compare_result:
        if hasattr(r, "text"):
            print(f"   {r.text}")

    # ステップ 8: キャプチャ一覧
    print("\n📋 Step 8: List all captures")
    list_result = await server._handle_list_captures({})
    for r in list_result:
        if hasattr(r, "text"):
            print(f"   {r.text}")

    # ブラウザを閉じる
    print("\n🔚 Closing browser...")
    await server._handle_close_browser({})

    print("\n✅ Test completed!")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="ColonyForge Extension Visual Test")
    parser.add_argument("--url", help="VS Code / code-server URL")
    parser.add_argument("--demo", action="store_true", help="Use demo HTML page")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")

    args = parser.parse_args()

    if args.demo:
        url = await create_demo_page()
        print(f"Created demo page: {url}")
    elif args.url:
        url = args.url
    else:
        # デフォルトはcode-server
        url = os.environ.get("CODE_SERVER_URL", "http://localhost:8080")

    await run_test(url, headless=args.headless)


if __name__ == "__main__":
    asyncio.run(main())
