"""ColonyForge VS Code拡張のE2Eビジュアルテスト

pytestで実行可能なE2Eテストスイート。
Agent UIを使用してColonyForgeのUI要素をVLMで検証します。

実行方法:
    # 全E2Eテスト
    pytest tests/e2e/ -v

    # 通常テストのみ（E2E除外）
    pytest -m "not e2e"
"""

import asyncio
import contextlib
import os
from collections.abc import Generator
from pathlib import Path

import pytest

# テスト環境設定
os.environ.setdefault("OLLAMA_BASE_URL", "http://colonyforge-dev-ollama:11434")
os.environ.setdefault("VLM_HEADLESS", "true")

# E2Eマーカーをモジュール全体に適用
# VLMの揺らぎ対策としてリトライを設定（最大2回リトライ）
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.flaky(reruns=2, reruns_delay=1),
]


@pytest.fixture
def demo_html_path() -> Generator[str, None, None]:
    """テスト用のデモHTMLページを作成するフィクスチャ"""
    # tests/e2e/から見た相対パス
    demo_html = Path(__file__).parent / "colonyforge_demo.html"

    # デモHTMLがなければ作成
    if not demo_html.exists():
        demo_html.write_text("""<!DOCTYPE html>
<html>
<head><title>ColonyForge Dashboard Demo</title></head>
<body style="background:#1e1e1e;color:#ccc;font-family:sans-serif;">
<div style="display:flex;">
<div style="width:260px;background:#252526;padding:10px;">
<h3>ColonyForge</h3>
<div><h4>RUNS</h4><div>Run-001 (実行中)</div></div>
<div><h4>TASKS</h4><div>Task-001: テスト</div></div>
<div><h4>確認要請</h4><div>デザイン確認</div></div>
</div>
<div style="flex:1;padding:20px;">
<h1>🐝 ColonyForge Dashboard</h1>
<p>Welcome to ColonyForge</p>
</div>
</div>
</body>
</html>""")

    yield f"file://{demo_html.absolute()}"

    # 後処理（ファイルは残す）


@pytest.fixture
async def agent_ui_server():
    """Agent UI サーバーのフィクスチャ"""
    from colonyforge.agent_ui.server import AgentUIMCPServer

    captures_dir = Path(__file__).parent / "test_captures_e2e"
    captures_dir.mkdir(exist_ok=True)

    server = AgentUIMCPServer(captures_dir=str(captures_dir))
    yield server

    # クリーンアップ: ブラウザを閉じる
    with contextlib.suppress(Exception):
        await server._handle_close_browser({})


def get_text_from_result(result: list) -> str:
    """結果リストからテキストを抽出するヘルパー"""
    for r in result:
        if hasattr(r, "text"):
            return r.text
    return ""


class TestColonyForgeExtensionVisual:
    """ColonyForge拡張のビジュアルテストクラス"""

    @pytest.mark.asyncio
    async def test_can_navigate_to_colonyforge_page(self, agent_ui_server, demo_html_path: str):
        """ColonyForgeページへ遷移できることを確認"""
        # Act
        result = await agent_ui_server._handle_navigate({"url": demo_html_path})

        # Assert
        assert len(result) > 0
        assert "Navigated to" in result[0].text

    @pytest.mark.asyncio
    async def test_can_capture_screen(self, agent_ui_server, demo_html_path: str):
        """画面キャプチャができることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(0.5)

        # Act
        result = await agent_ui_server._handle_capture_screen({"save": True})

        # Assert
        assert len(result) > 0
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        assert "Captured" in text or "Saved" in text

    @pytest.mark.asyncio
    async def test_vlm_recognizes_colonyforge_dashboard(self, agent_ui_server, demo_html_path: str):
        """VLMがColonyForgeダッシュボードを認識できることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_describe_page(
            {"focus": "What is this page? Is it ColonyForge? What sections are visible?"}
        )

        # Assert
        assert len(result) > 0
        analysis = get_text_from_result(result).lower()
        # VLMがColonyForge関連のキーワードまたは画面の説明を認識すること
        expected_words = [
            "colonyforge",
            "dashboard",
            "runs",
            "tasks",
            "sidebar",
            "panel",
            "section",
            "header",
            "welcome",
        ]
        assert any(word in analysis for word in expected_words), f"VLM response: {analysis[:500]}"

    @pytest.mark.asyncio
    async def test_vlm_identifies_runs_section(self, agent_ui_server, demo_html_path: str):
        """VLMがRunsセクションを識別できることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_describe_page(
            {"focus": "Is there a Runs section visible? What runs are listed?"}
        )

        # Assert
        assert len(result) > 0
        analysis = get_text_from_result(result).lower()
        assert any(word in analysis for word in ["run", "runs", "実行"])

    @pytest.mark.asyncio
    async def test_vlm_identifies_tasks_section(self, agent_ui_server, demo_html_path: str):
        """VLMがTasksセクションを識別できることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_describe_page(
            {"focus": "Is there a Tasks section visible? What tasks are shown?"}
        )

        # Assert
        assert len(result) > 0
        analysis = get_text_from_result(result).lower()
        assert any(word in analysis for word in ["task", "tasks", "タスク"])

    @pytest.mark.asyncio
    async def test_vlm_identifies_requirements_section(self, agent_ui_server, demo_html_path: str):
        """VLMが確認要請セクションを識別できることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_describe_page(
            {"focus": "Is there a Requirements or 確認要請 section visible?"}
        )

        # Assert
        assert len(result) > 0
        analysis = get_text_from_result(result).lower()
        # VLMが確認要請関連のキーワードまたは画面の説明を認識すること
        expected_words = [
            "requirement",
            "確認",
            "request",
            "approval",
            "section",
            "sidebar",
            "panel",
            "text",
            "heading",
        ]
        assert any(word in analysis for word in expected_words), f"VLM response: {analysis[:500]}"

    @pytest.mark.asyncio
    async def test_can_click_on_page(self, agent_ui_server, demo_html_path: str):
        """ページ上でクリックできることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(0.5)

        # Act - 画面中央をクリック
        result = await agent_ui_server._handle_click({"x": 400, "y": 300})

        # Assert
        assert len(result) > 0
        text = get_text_from_result(result)
        # 日本語（クリックしました）または英語（Click）を受け入れる
        assert any(word in text for word in ["Click", "click", "クリック"])

    @pytest.mark.asyncio
    async def test_screen_compare_detects_no_change_for_same_page(
        self, agent_ui_server, demo_html_path: str
    ):
        """同じページで画面比較すると変化なしと判定されることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_compare({})

        # Assert
        assert len(result) > 0
        text = result[0].text.lower()
        # 変化なしまたは同じであることを示すメッセージ
        assert any(word in text for word in ["変化", "same", "similar", "なし", "no change"])

    @pytest.mark.asyncio
    async def test_list_captures_shows_history(self, agent_ui_server, demo_html_path: str):
        """キャプチャ履歴が表示されることを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await agent_ui_server._handle_capture_screen({"save": True})

        # Act
        result = await agent_ui_server._handle_list_captures({})

        # Assert
        assert len(result) > 0
        text = result[0].text
        # JSONまたはリスト形式で履歴が返される
        assert "[" in text or "timestamp" in text.lower() or "capture" in text.lower()


class TestColonyForgeElementFinding:
    """ColonyForge要素探索のテストクラス"""

    @pytest.mark.asyncio
    async def test_find_element_returns_result(self, agent_ui_server, demo_html_path: str):
        """要素探索が結果を返すことを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})
        await asyncio.sleep(1)
        await agent_ui_server._handle_capture_screen({})

        # Act
        result = await agent_ui_server._handle_find_element(
            {"description": "ColonyForge Dashboard title"}
        )

        # Assert
        assert len(result) > 0
        # VLMからの応答があること
        assert result[0].text is not None

    @pytest.mark.asyncio
    async def test_type_text_works(self, agent_ui_server, demo_html_path: str):
        """テキスト入力が動作することを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})

        # Act
        result = await agent_ui_server._handle_type_text({"text": "test input"})

        # Assert
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_press_key_works(self, agent_ui_server, demo_html_path: str):
        """キー入力が動作することを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})

        # Act
        result = await agent_ui_server._handle_press_key({"key": "Tab"})

        # Assert
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_scroll_works(self, agent_ui_server, demo_html_path: str):
        """スクロールが動作することを確認"""
        # Arrange
        await agent_ui_server._handle_navigate({"url": demo_html_path})

        # Act
        result = await agent_ui_server._handle_scroll({"direction": "down", "amount": 100})

        # Assert
        assert len(result) > 0
