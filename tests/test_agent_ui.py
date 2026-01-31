"""Agent UI MCP Server のテスト"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiveforge.agent_ui.server import AgentUIMCPServer, BrowserSession


class TestBrowserSession:
    """BrowserSession のテスト"""

    def test_initial_state(self):
        """初期状態ではブラウザは起動していない"""
        # Arrange & Act
        with patch.dict(os.environ, {}, clear=True):
            session = BrowserSession()

        # Assert
        assert session.page is None

    @pytest.mark.asyncio
    async def test_ensure_browser_starts_browser_playwright_mode(self):
        """ensure_browser()でPlaywrightモードでブラウザが起動する（MCP URL未設定時）"""
        # Arrange
        with patch.dict(os.environ, {"PLAYWRIGHT_MCP_URL": ""}, clear=False):
            session = BrowserSession()
            session._use_mcp = False  # 強制的にPlaywrightモード

        # Act
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            mock_browser = AsyncMock()
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

            mock_page = AsyncMock()
            mock_browser.new_page = AsyncMock(return_value=mock_page)

            await session.ensure_browser()

            # Assert
            assert session.page is not None

    @pytest.mark.asyncio
    async def test_ensure_browser_starts_mcp_mode(self):
        """ensure_browser()でMCPモードでクライアントが初期化される"""
        # Arrange
        session = BrowserSession()
        session._use_mcp = True  # 強制的にMCPモード

        # Act
        await session.ensure_browser()

        # Assert
        assert session.mcp_client is not None
        assert session.using_mcp is True

    @pytest.mark.asyncio
    async def test_close_resets_state(self):
        """close()で状態がリセットされる"""
        # Arrange
        session = BrowserSession()
        session._page = MagicMock()
        session._browser = AsyncMock()
        session._playwright = AsyncMock()

        # Act
        await session.close()

        # Assert
        assert session.page is None


class TestAgentUIMCPServer:
    """AgentUIMCPServer のテスト"""

    def test_init_creates_captures_dir(self):
        """初期化時にキャプチャディレクトリが作成される"""
        # Arrange & Act
        with tempfile.TemporaryDirectory() as tmpdir:
            captures_dir = Path(tmpdir) / "captures"
            server = AgentUIMCPServer(captures_dir=str(captures_dir))

            # Assert
            assert captures_dir.exists()
            assert captures_dir.is_dir()

    def test_server_name_is_agent_ui(self):
        """サーバー名が'agent-ui'である"""
        # Arrange & Act
        with tempfile.TemporaryDirectory() as tmpdir:
            server = AgentUIMCPServer(captures_dir=tmpdir)

            # Assert
            assert server.server.name == "agent-ui"

    def test_save_capture_stores_image_and_metadata(self):
        """キャプチャを保存すると画像とメタデータが保存される"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            server = AgentUIMCPServer(captures_dir=tmpdir)
            image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            metadata = {"action": "test"}

            # Act
            filepath = server._save_capture(image_data, metadata)

            # Assert
            assert Path(filepath).exists()

            json_files = list(server.captures_dir.glob("*.json"))
            assert len(json_files) == 1

            meta = json.loads(json_files[0].read_text())
            assert meta["action"] == "test"
            assert "timestamp" in meta


class TestAgentUITools:
    """Agent UI ツールのテスト"""

    @pytest.fixture
    def server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield AgentUIMCPServer(captures_dir=tmpdir)

    @pytest.mark.asyncio
    async def test_navigate(self, server):
        """navigate ツールがURLに移動する"""
        # Arrange
        mock_page = AsyncMock()
        server.session._page = mock_page
        server.session._capture = MagicMock()
        server.session._executor = MagicMock()

        # Act
        result = await server._handle_navigate({"url": "https://example.com"})

        # Assert
        mock_page.goto.assert_called_once_with("https://example.com")
        assert "example.com" in result[0].text

    @pytest.mark.asyncio
    async def test_type_text(self, server):
        """type_text ツールがテキストを入力する"""
        # Arrange
        mock_executor = AsyncMock()
        server.session._page = MagicMock()
        server.session._capture = MagicMock()
        server.session._executor = mock_executor

        # Act
        result = await server._handle_type_text({"text": "hello", "press_enter": True})

        # Assert
        mock_executor.type_text.assert_called_once_with("hello", press_enter=True)
        assert "hello" in result[0].text
        assert "Enter" in result[0].text

    @pytest.mark.asyncio
    async def test_press_key(self, server):
        """press_key ツールがキーを押す"""
        # Arrange
        mock_executor = AsyncMock()
        server.session._page = MagicMock()
        server.session._capture = MagicMock()
        server.session._executor = mock_executor

        # Act
        result = await server._handle_press_key({"key": "escape"})

        # Assert
        mock_executor.press_key.assert_called_once_with("escape")
        assert "escape" in result[0].text

    @pytest.mark.asyncio
    async def test_scroll(self, server):
        """scroll ツールがスクロールする"""
        # Arrange
        mock_executor = AsyncMock()
        mock_page = MagicMock()
        mock_page.viewport_size = {"width": 800, "height": 600}
        server.session._page = mock_page
        server.session._capture = MagicMock()
        server.session._executor = mock_executor

        # Act
        result = await server._handle_scroll({"direction": "down", "amount": 500})

        # Assert
        mock_executor.scroll.assert_called_once()
        call_args = mock_executor.scroll.call_args
        assert call_args.kwargs["delta_y"] == 500
        assert "down" in result[0].text

    @pytest.mark.asyncio
    async def test_close_browser(self, server):
        """close_browser ツールがブラウザを閉じる"""
        # Arrange
        server.session._browser = AsyncMock()
        server.session._playwright = AsyncMock()
        server.session._page = MagicMock()

        # Act
        result = await server._handle_close_browser({})

        # Assert
        assert server.session.page is None
        assert "閉じました" in result[0].text

    @pytest.mark.asyncio
    async def test_list_captures_empty(self, server):
        """list_captures は空のディレクトリで空のリストを返す"""
        # Act
        result = await server._handle_list_captures({"limit": 10})

        # Assert
        data = json.loads(result[0].text)
        assert data == []

    @pytest.mark.asyncio
    async def test_list_captures_with_files(self, server):
        """list_captures は保存されたキャプチャを返す"""
        # Arrange
        server._save_capture(b"png1", {"action": "action1"})
        server._save_capture(b"png2", {"action": "action2"})

        # Act
        result = await server._handle_list_captures({"limit": 10})

        # Assert
        data = json.loads(result[0].text)
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_compare_without_previous(self, server):
        """compare_with_previous は前回キャプチャがない場合エラーメッセージを返す"""
        # Arrange
        server._last_capture = None
        # MCPモードに設定してブラウザ起動をスキップ
        server.session._use_mcp = True
        server.session._capture = MagicMock()
        server.session._capture.capture = AsyncMock(return_value=b"current_image")
        server.session._executor = MagicMock()

        # Act
        result = await server._handle_compare({})

        # Assert
        assert "前回のキャプチャがありません" in result[0].text
