#!/usr/bin/env python3
"""HiveForge VS Code拡張のビジュアルテスト

Agent UIを使用してVS Code内のHiveForge拡張機能をテストします。
code-serverまたはVS Code (headless) を起動して、PlaywrightでUIを操作します。
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

# 環境設定
os.environ["OLLAMA_BASE_URL"] = "http://hiveforge-dev-ollama:11434"
os.environ["VLM_HEADLESS"] = "true"


class HiveForgeExtensionTest:
    """HiveForge拡張機能のテストクラス"""

    def __init__(self, server):
        self.server = server
        self.test_results: list[dict] = []
        self.screenshots_dir = Path("./test_results")
        self.screenshots_dir.mkdir(exist_ok=True)

    async def setup(self, vscode_url: str):
        """テストのセットアップ: VS Codeを開く"""
        print(f"\n🔧 セットアップ: {vscode_url} に接続...")
        result = await self.server._handle_navigate({"url": vscode_url})
        print(f"   {result[0].text}")

        # 読み込み待機
        await asyncio.sleep(3)

    async def capture_and_describe(self, test_name: str, description: str = "") -> dict:
        """キャプチャして説明を取得"""
        print(f"\n📸 {test_name}")

        # キャプチャ
        capture_result = await self.server._handle_capture_screen({"save": True})
        filepath = None
        for r in capture_result:
            if hasattr(r, "text") and "Saved" in r.text:
                filepath = r.text.split(": ")[1] if ": " in r.text else None

        # VLMで分析
        describe_result = await self.server._handle_describe_page({"focus": description})

        vlm_response = ""
        for r in describe_result:
            if hasattr(r, "text"):
                vlm_response = r.text

        result = {
            "test_name": test_name,
            "timestamp": datetime.now().isoformat(),
            "screenshot": filepath,
            "vlm_analysis": vlm_response[:500] if vlm_response else "",
        }
        self.test_results.append(result)

        print(f"   Screenshot: {filepath}")
        if vlm_response:
            print(f"   VLM: {vlm_response[:150]}...")

        return result

    async def click_activity_bar_icon(self, icon_name: str):
        """アクティビティバーのアイコンをクリック"""
        print(f"\n🖱️ アクティビティバー: {icon_name} をクリック")

        # VLMで位置を特定
        find_result = await self.server._handle_find_element(
            {"description": f"Activity bar icon for {icon_name} (left sidebar icons)"}
        )

        response = find_result[0].text if find_result else ""
        print(f"   VLM response: {response[:200]}")

        # 座標が見つかったらクリック（見つからない場合は推定位置をクリック）
        try:
            import json

            data = json.loads(response)
            if data.get("found"):
                await self.server._handle_click({"x": data["x"], "y": data["y"]})
                return True
        except Exception:
            pass

        # フォールバック: アクティビティバーは通常左端にある
        # HiveForgeアイコンは下の方にあると想定
        await self.server._handle_click({"x": 25, "y": 400})
        return False

    async def test_hiveforge_sidebar_visible(self):
        """テスト: HiveForgeサイドバーが表示されているか"""
        print("\n" + "=" * 60)
        print("テスト 1: HiveForgeサイドバーの表示確認")
        print("=" * 60)

        # HiveForgeアイコンをクリック
        await self.click_activity_bar_icon("HiveForge")
        await asyncio.sleep(1)

        # キャプチャして確認
        result = await self.capture_and_describe(
            "HiveForge Sidebar",
            "Look for HiveForge views: Runs, Tasks, 確認要請 (requirements). Is the HiveForge sidebar visible?",
        )

        # 結果判定（VLM応答から判断）
        analysis = result["vlm_analysis"].lower()
        passed = any(word in analysis for word in ["hiveforge", "runs", "tasks", "sidebar"])

        print(f"   結果: {'✅ PASS' if passed else '❌ FAIL'}")
        result["passed"] = passed
        return result

    async def test_runs_view(self):
        """テスト: Runsビューの確認"""
        print("\n" + "=" * 60)
        print("テスト 2: Runsビューの確認")
        print("=" * 60)

        # Runsビューをクリック
        await self.server._handle_click({"element": "Runs section header"})
        await asyncio.sleep(0.5)

        result = await self.capture_and_describe(
            "Runs View",
            "Look for the Runs view in HiveForge sidebar. Is it expanded? Are there any runs listed?",
        )

        analysis = result["vlm_analysis"].lower()
        passed = "run" in analysis
        print(f"   結果: {'✅ PASS' if passed else '❌ FAIL'}")
        result["passed"] = passed
        return result

    async def test_tasks_view(self):
        """テスト: Tasksビューの確認"""
        print("\n" + "=" * 60)
        print("テスト 3: Tasksビューの確認")
        print("=" * 60)

        result = await self.capture_and_describe(
            "Tasks View", "Look for the Tasks view in HiveForge sidebar. Can you see task items?"
        )

        analysis = result["vlm_analysis"].lower()
        passed = "task" in analysis
        print(f"   結果: {'✅ PASS' if passed else '❌ FAIL'}")
        result["passed"] = passed
        return result

    async def test_requirements_view(self):
        """テスト: 確認要請ビューの確認"""
        print("\n" + "=" * 60)
        print("テスト 4: 確認要請ビューの確認")
        print("=" * 60)

        result = await self.capture_and_describe(
            "Requirements View", "Look for '確認要請' (requirements) view in HiveForge sidebar."
        )

        analysis = result["vlm_analysis"].lower()
        passed = any(word in analysis for word in ["requirement", "確認", "request"])
        print(f"   結果: {'✅ PASS' if passed else '❌ FAIL'}")
        result["passed"] = passed
        return result

    async def test_command_palette(self):
        """テスト: コマンドパレットからHiveForgeコマンドを確認"""
        print("\n" + "=" * 60)
        print("テスト 5: コマンドパレットのHiveForgeコマンド")
        print("=" * 60)

        # Ctrl+Shift+Pでコマンドパレットを開く
        await self.server._handle_press_key({"key": "ctrl+shift+p"})
        await asyncio.sleep(0.5)

        # "HiveForge"と入力
        await self.server._handle_type_text({"text": "HiveForge"})
        await asyncio.sleep(0.5)

        result = await self.capture_and_describe(
            "Command Palette - HiveForge",
            "Look at the command palette. Are HiveForge commands visible? List the commands you can see.",
        )

        # Escで閉じる
        await self.server._handle_press_key({"key": "escape"})

        analysis = result["vlm_analysis"].lower()
        passed = any(word in analysis for word in ["hiveforge", "dashboard", "run", "command"])
        print(f"   結果: {'✅ PASS' if passed else '❌ FAIL'}")
        result["passed"] = passed
        return result

    async def run_all_tests(self, vscode_url: str):
        """全テストを実行"""
        print("\n" + "=" * 60)
        print("🧪 HiveForge VS Code Extension ビジュアルテスト")
        print("=" * 60)

        await self.setup(vscode_url)

        tests = [
            self.test_hiveforge_sidebar_visible,
            self.test_runs_view,
            self.test_tasks_view,
            self.test_requirements_view,
            self.test_command_palette,
        ]

        for test in tests:
            try:
                await test()
            except Exception as e:
                print(f"   ❌ エラー: {e}")
                self.test_results.append(
                    {
                        "test_name": test.__name__,
                        "error": str(e),
                        "passed": False,
                    }
                )

        # 結果サマリー
        self.print_summary()

        # ブラウザを閉じる
        await self.server._handle_close_browser({})

    def print_summary(self):
        """テスト結果のサマリーを表示"""
        print("\n" + "=" * 60)
        print("📊 テスト結果サマリー")
        print("=" * 60)

        passed = sum(1 for r in self.test_results if r.get("passed", False))
        total = len(self.test_results)

        for r in self.test_results:
            status = "✅" if r.get("passed") else "❌"
            print(f"   {status} {r.get('test_name', 'Unknown')}")

        print(f"\n   合計: {passed}/{total} テスト通過")

        # 結果をJSONで保存
        import json

        result_file = self.screenshots_dir / "test_results.json"
        result_file.write_text(json.dumps(self.test_results, indent=2, ensure_ascii=False))
        print(f"\n   結果ファイル: {result_file}")


async def main():
    """メイン関数"""
    from hiveforge.agent_ui.server import AgentUIMCPServer

    # VS Codeの URL（code-server または VS Code の URL）
    # devcontainer内では通常 http://localhost:8080 または環境変数から取得
    vscode_url = os.environ.get("CODE_SERVER_URL", "http://localhost:8080")

    print(f"VS Code URL: {vscode_url}")
    print("（環境変数 CODE_SERVER_URL で変更可能）")

    server = AgentUIMCPServer(captures_dir="./test_results/captures")
    tester = HiveForgeExtensionTest(server)

    await tester.run_all_tests(vscode_url)


if __name__ == "__main__":
    asyncio.run(main())
