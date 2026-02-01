"""Agent UI MCP Server のテスト"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiveforge.agent_ui.server import AgentUIMCPServer, BrowserSession


class TestBrowserSession:
    """BrowserSession のテスト"""

    def test_initial_state(self):
        """初期状態ではブラウザは起動していない"""
        # Arrange & Act
        session = BrowserSession()

        # Assert
        assert session.mcp_client is None

    @pytest.mark.asyncio
    async def test_ensure_browser_creates_mcp_client(self):
        """ensure_browser()でMCPクライアントが初期化される"""
        # Arrange
        session = BrowserSession()

        # Act
        await session.ensure_browser()

        # Assert
        assert session.mcp_client is not None
        assert session._capture is not None
        assert session._executor is not None

    @pytest.mark.asyncio
    async def test_close_resets_state(self):
        """close()で状態がリセットされる"""
        # Arrange
        session = BrowserSession()
        session._mcp_client = MagicMock()
        session._mcp_client.close = AsyncMock()
        session._capture = MagicMock()
        session._executor = MagicMock()

        # Act
        await session.close()

        # Assert
        assert session.mcp_client is None
        assert session._capture is None
        assert session._executor is None


class TestAgentUIMCPServer:
    """AgentUIMCPServer のテスト"""

    def test_init_creates_captures_dir(self):
        """初期化時にキャプチャディレクトリが作成される"""
        # Arrange & Act
        with tempfile.TemporaryDirectory() as tmpdir:
            captures_dir = Path(tmpdir) / "captures"
            AgentUIMCPServer(captures_dir=str(captures_dir))

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
        mock_mcp_client = AsyncMock()
        server.session._mcp_client = mock_mcp_client
        server.session._capture = MagicMock()
        server.session._executor = MagicMock()

        # Act
        result = await server._handle_navigate({"url": "https://example.com"})

        # Assert
        mock_mcp_client.navigate.assert_called_once_with("https://example.com")
        assert "example.com" in result[0].text

    @pytest.mark.asyncio
    async def test_type_text(self, server):
        """type_text ツールがテキストを入力する"""
        # Arrange
        mock_executor = AsyncMock()
        server.session._mcp_client = MagicMock()
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
        server.session._mcp_client = MagicMock()
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
        mock_mcp_client = MagicMock()
        mock_mcp_client.get_viewport_size = MagicMock(return_value={"width": 800, "height": 600})
        server.session._mcp_client = mock_mcp_client
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
        mock_mcp_client = AsyncMock()
        server.session._mcp_client = mock_mcp_client
        server.session._capture = MagicMock()
        server.session._executor = MagicMock()

        # Act
        result = await server._handle_close_browser({})

        # Assert
        mock_mcp_client.close.assert_called_once()
        assert server.session.mcp_client is None
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
        server.session._mcp_client = MagicMock()
        server.session._capture = MagicMock()
        server.session._capture.capture = AsyncMock(return_value=b"current_image")
        server.session._executor = MagicMock()

        # Act
        result = await server._handle_compare({})

        # Assert
        assert "前回のキャプチャがありません" in result[0].text


class TestAgentUIHandlers:
    """AgentUIHandlers クラスの詳細テスト"""

    @pytest.fixture
    def handlers_with_mocks(self):
        """モック化されたハンドラー"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_session = MagicMock()
            mock_session.ensure_browser = AsyncMock()
            mock_session.navigate = AsyncMock()
            mock_session.close = AsyncMock()

            mock_capture = AsyncMock()
            mock_capture.capture = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            mock_session.capture = mock_capture

            mock_executor = AsyncMock()
            mock_session.executor = mock_executor

            from hiveforge.agent_ui.handlers import AgentUIHandlers
            from hiveforge.vlm_tester.hybrid_analyzer import HybridAnalyzer
            from hiveforge.vlm_tester.local_analyzers import DiffAnalyzer

            mock_analyzer = MagicMock(spec=HybridAnalyzer)
            mock_diff_analyzer = MagicMock(spec=DiffAnalyzer)

            handlers = AgentUIHandlers(
                session=mock_session,
                captures_dir=Path(tmpdir),
                analyzer=mock_analyzer,
                diff_analyzer=mock_diff_analyzer,
            )

            yield handlers, mock_session, mock_analyzer, mock_diff_analyzer

    @pytest.mark.asyncio
    async def test_handle_navigate(self, handlers_with_mocks):
        """navigate ハンドラがURLに移動する"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_navigate({"url": "https://example.com"})

        # Assert
        mock_session.ensure_browser.assert_called_once()
        mock_session.navigate.assert_called_once_with("https://example.com")
        assert "example.com" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_capture_screen_with_save(self, handlers_with_mocks):
        """capture_screen ハンドラが画像を保存する"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_capture_screen({"save": True})

        # Assert
        mock_session.ensure_browser.assert_called_once()
        mock_session.capture.capture.assert_called_once()
        # TextContent(保存パス) + ImageContent(画像)
        assert len(result) == 2
        assert "Saved:" in result[0].text
        assert result[1].type == "image"

    @pytest.mark.asyncio
    async def test_handle_capture_screen_without_save(self, handlers_with_mocks):
        """capture_screen ハンドラがsave=Falseで画像のみ返す"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_capture_screen({"save": False})

        # Assert
        # ImageContentのみ
        assert len(result) == 1
        assert result[0].type == "image"

    @pytest.mark.asyncio
    async def test_handle_describe_page(self, handlers_with_mocks):
        """describe_page ハンドラがページを説明する"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = "ページの説明テキスト"
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_describe_page({"focus": "ボタン"})

        # Assert
        mock_session.ensure_browser.assert_called_once()
        mock_analyzer.analyze.assert_called_once()
        assert result[0].type == "image"
        assert "ページの説明テキスト" in result[1].text

    @pytest.mark.asyncio
    async def test_handle_describe_page_no_focus(self, handlers_with_mocks):
        """describe_page ハンドラがfocusなしでも動作する"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = "説明結果"
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_describe_page({})

        # Assert
        mock_analyzer.analyze.assert_called_once()
        assert "説明結果" in result[1].text

    @pytest.mark.asyncio
    async def test_handle_describe_page_no_result(self, handlers_with_mocks):
        """describe_page ハンドラが結果なしの場合のデフォルトテキスト"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = None
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_describe_page({})

        # Assert
        assert "分析結果なし" in result[1].text

    @pytest.mark.asyncio
    async def test_handle_find_element(self, handlers_with_mocks):
        """find_element ハンドラが要素を探す"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = '{"found": true, "x": 100, "y": 200}'
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_find_element({"description": "送信ボタン"})

        # Assert
        mock_analyzer.analyze.assert_called_once()
        assert "found" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_find_element_no_result(self, handlers_with_mocks):
        """find_element ハンドラが結果なしの場合"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = None
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_find_element({"description": "存在しない要素"})

        # Assert
        assert "分析失敗" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_compare_no_change(self, handlers_with_mocks):
        """compare ハンドラが変化なしを検出する"""
        # Arrange
        handlers, mock_session, _, mock_diff_analyzer = handlers_with_mocks
        handlers._last_capture = b"previous_image"

        mock_diff_result = MagicMock()
        mock_diff_result.data = {"is_same": True}
        mock_diff_analyzer.compare = AsyncMock(return_value=mock_diff_result)

        # Act
        result = await handlers.handle_compare({})

        # Assert
        assert "変化はありません" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_compare_with_change(self, handlers_with_mocks):
        """compare ハンドラが変化を検出する"""
        # Arrange
        handlers, mock_session, _, mock_diff_analyzer = handlers_with_mocks
        handlers._last_capture = b"previous_image"

        mock_diff_result = MagicMock()
        mock_diff_result.data = {"is_same": False, "diff_ratio": 0.15}
        mock_diff_analyzer.compare = AsyncMock(return_value=mock_diff_result)
        mock_diff_analyzer.create_diff_image = AsyncMock(return_value=b"diff_image_data")

        # Act
        result = await handlers.handle_compare({})

        # Assert
        assert result[0].type == "image"
        assert "変化があります" in result[1].text
        assert "15" in result[1].text  # 15%

    @pytest.mark.asyncio
    async def test_handle_compare_no_diff_image(self, handlers_with_mocks):
        """compare ハンドラが差分画像なしでも動作する"""
        # Arrange
        handlers, mock_session, _, mock_diff_analyzer = handlers_with_mocks
        handlers._last_capture = b"previous_image"

        mock_diff_result = MagicMock()
        mock_diff_result.data = {"is_same": False, "diff_ratio": 0.05}
        mock_diff_analyzer.compare = AsyncMock(return_value=mock_diff_result)
        mock_diff_analyzer.create_diff_image = AsyncMock(return_value=None)

        # Act
        result = await handlers.handle_compare({})

        # Assert
        assert len(result) == 1
        assert "変化があります" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_click_with_coordinates(self, handlers_with_mocks):
        """click ハンドラが座標でクリックする"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_click({"x": 100, "y": 200})

        # Assert
        mock_session.executor.click.assert_called_once_with(100, 200, double_click=False)
        assert "クリックしました" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_click_double_click(self, handlers_with_mocks):
        """click ハンドラがダブルクリックする"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_click({"x": 100, "y": 200, "double_click": True})

        # Assert
        mock_session.executor.click.assert_called_once_with(100, 200, double_click=True)
        assert "ダブルクリック" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_click_with_element_found(self, handlers_with_mocks):
        """click ハンドラが要素指定でクリックする（要素発見）"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = '{"found": true, "x": 150, "y": 250}'
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_click({"element": "送信ボタン"})

        # Assert
        mock_session.executor.click.assert_called_once_with(150, 250, double_click=False)
        assert "クリックしました" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_click_with_element_not_found(self, handlers_with_mocks):
        """click ハンドラが要素指定でクリックする（要素未発見）"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = '{"found": false, "reason": "見つからない"}'
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_click({"element": "存在しないボタン"})

        # Assert
        mock_session.executor.click.assert_not_called()
        assert "見つかりませんでした" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_click_with_element_json_error(self, handlers_with_mocks):
        """click ハンドラが要素指定でJSONパースエラー"""
        # Arrange
        handlers, mock_session, mock_analyzer, _ = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = "invalid json"
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_click({"element": "ボタン"})

        # Assert
        mock_session.executor.click.assert_not_called()
        assert "特定できませんでした" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_click_no_coordinates(self, handlers_with_mocks):
        """click ハンドラが座標も要素もない場合エラー"""
        # Arrange
        handlers, _, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_click({})

        # Assert
        assert "座標" in result[0].text or "element" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_type_text(self, handlers_with_mocks):
        """type_text ハンドラがテキストを入力する"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_type_text({"text": "Hello World"})

        # Assert
        mock_session.executor.type_text.assert_called_once_with("Hello World", press_enter=False)
        assert "入力しました" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_type_text_with_enter(self, handlers_with_mocks):
        """type_text ハンドラがEnterも押す"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_type_text({"text": "検索ワード", "press_enter": True})

        # Assert
        mock_session.executor.type_text.assert_called_once_with("検索ワード", press_enter=True)
        assert "Enter" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_press_key(self, handlers_with_mocks):
        """press_key ハンドラがキーを押す"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_press_key({"key": "Enter"})

        # Assert
        mock_session.executor.press_key.assert_called_once_with("Enter")
        assert "Enter" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_scroll_down(self, handlers_with_mocks):
        """scroll ハンドラが下にスクロールする"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_scroll({"direction": "down", "amount": 500})

        # Assert
        mock_session.executor.scroll.assert_called_once()
        call_kwargs = mock_session.executor.scroll.call_args.kwargs
        assert call_kwargs["delta_y"] == 500
        assert "down" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_scroll_up(self, handlers_with_mocks):
        """scroll ハンドラが上にスクロールする"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        await handlers.handle_scroll({"direction": "up"})

        # Assert
        call_kwargs = mock_session.executor.scroll.call_args.kwargs
        assert call_kwargs["delta_y"] == -300  # default amount

    @pytest.mark.asyncio
    async def test_handle_scroll_right(self, handlers_with_mocks):
        """scroll ハンドラが右にスクロールする"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        await handlers.handle_scroll({"direction": "right", "amount": 200})

        # Assert
        call_kwargs = mock_session.executor.scroll.call_args.kwargs
        assert call_kwargs["delta_x"] == 200

    @pytest.mark.asyncio
    async def test_handle_scroll_left(self, handlers_with_mocks):
        """scroll ハンドラが左にスクロールする"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        await handlers.handle_scroll({"direction": "left", "amount": 100})

        # Assert
        call_kwargs = mock_session.executor.scroll.call_args.kwargs
        assert call_kwargs["delta_x"] == -100

    @pytest.mark.asyncio
    async def test_handle_close_browser(self, handlers_with_mocks):
        """close_browser ハンドラがブラウザを閉じる"""
        # Arrange
        handlers, mock_session, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_close_browser({})

        # Assert
        mock_session.close.assert_called_once()
        assert "閉じました" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_list_captures_empty(self, handlers_with_mocks):
        """list_captures ハンドラが空のリストを返す"""
        # Arrange
        handlers, _, _, _ = handlers_with_mocks

        # Act
        result = await handlers.handle_list_captures({})

        # Assert
        data = json.loads(result[0].text)
        assert data == []

    @pytest.mark.asyncio
    async def test_handle_list_captures_with_files(self, handlers_with_mocks):
        """list_captures ハンドラがファイル一覧を返す"""
        # Arrange
        handlers, _, _, _ = handlers_with_mocks
        # テスト用のキャプチャファイルを作成
        handlers._save_capture(b"test_image", {"action": "test_action"})

        # Act
        result = await handlers.handle_list_captures({"limit": 5})

        # Assert
        data = json.loads(result[0].text)
        assert len(data) == 1
        assert data[0]["action"] == "test_action"

    @pytest.mark.asyncio
    async def test_handle_list_captures_with_limit(self, handlers_with_mocks):
        """list_captures ハンドラがlimitを適用する"""
        # Arrange
        handlers, _, _, _ = handlers_with_mocks
        for i in range(5):
            handlers._save_capture(b"test_image", {"action": f"action_{i}"})

        # Act
        result = await handlers.handle_list_captures({"limit": 3})

        # Assert
        data = json.loads(result[0].text)
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_handle_list_captures_invalid_json(self, handlers_with_mocks):
        """list_captures ハンドラが不正なJSONファイルをスキップする"""
        # Arrange
        handlers, _, _, _ = handlers_with_mocks
        # 正常なキャプチャ
        handlers._save_capture(b"test_image", {"action": "valid"})
        # 不正なJSONファイルを作成
        invalid_json_path = handlers.captures_dir / "invalid.json"
        invalid_json_path.write_text("invalid json content")

        # Act
        result = await handlers.handle_list_captures({})

        # Assert
        data = json.loads(result[0].text)
        assert len(data) == 1  # 正常なファイルのみ

    def test_save_capture(self, handlers_with_mocks):
        """_save_capture がファイルを保存する"""
        # Arrange
        handlers, _, _, _ = handlers_with_mocks
        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        metadata = {"action": "test", "extra": "data"}

        # Act
        filepath = handlers._save_capture(image_data, metadata)

        # Assert
        assert Path(filepath).exists()
        # メタデータファイルも存在
        json_files = list(handlers.captures_dir.glob("*.json"))
        assert len(json_files) == 1
        meta = json.loads(json_files[0].read_text())
        assert meta["action"] == "test"
        assert "timestamp" in meta
        assert "image_file" in meta


class TestAgentUIHandlersWaitForElement:
    """wait_for_element ハンドラーのテスト"""

    @pytest.fixture
    def handlers_with_mocks(self):
        """モック化されたハンドラー（タイムアウトテスト用）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_session = MagicMock()
            mock_session.ensure_browser = AsyncMock()

            mock_capture = AsyncMock()
            mock_capture.capture = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n")
            mock_session.capture = mock_capture

            from hiveforge.agent_ui.handlers import AgentUIHandlers
            from hiveforge.vlm_tester.hybrid_analyzer import HybridAnalyzer

            mock_analyzer = MagicMock(spec=HybridAnalyzer)

            handlers = AgentUIHandlers(
                session=mock_session,
                captures_dir=Path(tmpdir),
                analyzer=mock_analyzer,
            )

            yield handlers, mock_analyzer

    @pytest.mark.asyncio
    async def test_wait_for_element_found_immediately(self, handlers_with_mocks):
        """wait_for_element が要素をすぐに見つける"""
        # Arrange
        handlers, mock_analyzer = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = '{"found": true, "x": 100, "y": 200}'
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_wait_for_element({"description": "ボタン", "timeout": 5})

        # Assert
        assert "見つかりました" in result[0].text
        assert "100" in result[0].text
        assert "200" in result[0].text

    @pytest.mark.asyncio
    async def test_wait_for_element_timeout(self, handlers_with_mocks):
        """wait_for_element がタイムアウトする"""
        # Arrange
        handlers, mock_analyzer = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = '{"found": false}'
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act（短いタイムアウトを設定）
        result = await handlers.handle_wait_for_element(
            {"description": "存在しない要素", "timeout": 0.1}
        )

        # Assert
        assert "タイムアウト" in result[0].text

    @pytest.mark.asyncio
    async def test_wait_for_element_json_error(self, handlers_with_mocks):
        """wait_for_element がJSONエラーでもタイムアウト"""
        # Arrange
        handlers, mock_analyzer = handlers_with_mocks
        mock_result = MagicMock()
        mock_result.combined_text = "invalid json"
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        # Act
        result = await handlers.handle_wait_for_element({"description": "要素", "timeout": 0.1})

        # Assert
        assert "タイムアウト" in result[0].text


class TestBrowserSessionExtended:
    """BrowserSession の拡張テスト"""

    @pytest.mark.asyncio
    async def test_navigate_without_mcp_client_raises_error(self):
        """MCPクライアントなしでnavigate呼び出しはエラー"""
        # Arrange
        session = BrowserSession()

        # Act & Assert
        with pytest.raises(RuntimeError, match="MCP client not initialized"):
            await session.navigate("https://example.com")

    def test_capture_property_without_browser_raises_error(self):
        """ブラウザ未起動時にcaptureプロパティアクセスはエラー"""
        # Arrange
        session = BrowserSession()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = session.capture

    def test_executor_property_without_browser_raises_error(self):
        """ブラウザ未起動時にexecutorプロパティアクセスはエラー"""
        # Arrange
        session = BrowserSession()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = session.executor

    @pytest.mark.asyncio
    async def test_ensure_browser_only_initializes_once(self):
        """ensure_browserは一度だけ初期化する"""
        # Arrange
        session = BrowserSession()
        session._capture = MagicMock()  # 既に初期化済みをシミュレート
        original_capture = session._capture

        # Act
        await session.ensure_browser()

        # Assert（同じキャプチャオブジェクトのまま）
        assert session._capture is original_capture


class TestAgentUIServerExtended:
    """AgentUIMCPServer の拡張テスト"""

    def test_analyzer_property(self):
        """analyzerプロパティがハンドラーのanalyzerを返す"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            server = AgentUIMCPServer(captures_dir=tmpdir)

            # Act & Assert
            assert server.analyzer is server.handlers.analyzer

    def test_diff_analyzer_property(self):
        """diff_analyzerプロパティがハンドラーのdiff_analyzerを返す"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            server = AgentUIMCPServer(captures_dir=tmpdir)

            # Act & Assert
            assert server.diff_analyzer is server.handlers.diff_analyzer

    def test_last_capture_getter_setter(self):
        """_last_captureプロパティの取得・設定"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            server = AgentUIMCPServer(captures_dir=tmpdir)

            # Act
            server._last_capture = b"test_data"

            # Assert
            assert server._last_capture == b"test_data"
            assert server.handlers._last_capture == b"test_data"


class TestAgentUIToolDefinitions:
    """Agent UI ツール定義のテスト"""

    def test_get_tool_definitions_returns_list(self):
        """get_tool_definitionsがToolのリストを返す"""
        # Arrange
        from hiveforge.agent_ui.tools import get_tool_definitions

        # Act
        tools = get_tool_definitions()

        # Assert
        assert isinstance(tools, list)
        assert len(tools) > 0
        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "inputSchema")

    def test_tool_definitions_include_required_tools(self):
        """必須ツールが含まれている"""
        # Arrange
        from hiveforge.agent_ui.tools import get_tool_definitions

        # Act
        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        # Assert
        required_tools = [
            "navigate",
            "capture_screen",
            "describe_page",
            "find_element",
            "click",
            "type_text",
            "press_key",
            "scroll",
            "close_browser",
            "list_captures",
        ]
        for required in required_tools:
            assert required in tool_names, f"{required} should be in tool definitions"
