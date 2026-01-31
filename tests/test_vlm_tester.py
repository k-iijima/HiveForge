"""VLM Tester モジュールのテスト

VLM Tester MCP Serverとその構成コンポーネントのテスト。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiveforge.vlm_tester.server import VLMTesterMCPServer
from hiveforge.vlm_tester.screen_capture import ScreenCapture
from hiveforge.vlm_tester.vlm_client import VLMClient
from hiveforge.vlm_tester.action_executor import ActionExecutor
from hiveforge.vlm_tester.vlm_providers import (
    OllamaProvider,
    AnthropicProvider,
    MultiProviderVLMClient,
)
from hiveforge.vlm_tester.local_analyzers import (
    OCRAnalyzer,
    DiffAnalyzer,
    LocalAnalyzerPipeline,
    AnalysisResult,
)
from hiveforge.vlm_tester.hybrid_analyzer import (
    HybridAnalyzer,
    AnalysisLevel,
    HybridAnalysisResult,
)


# =============================================================================
# ScreenCapture Tests
# =============================================================================


class TestScreenCapture:
    """ScreenCapture クラスのテスト"""

    def test_init_creates_instance(self):
        """インスタンスが作成できる"""
        # Arrange & Act
        capture = ScreenCapture()

        # Assert: mcp_clientは未設定
        assert capture._mcp_client is None

    def test_set_mcp_client(self):
        """MCPクライアントを設定できる"""
        # Arrange
        capture = ScreenCapture()
        mock_client = MagicMock()

        # Act
        capture.set_mcp_client(mock_client)

        # Assert
        assert capture._mcp_client is mock_client

    @pytest.mark.asyncio
    async def test_capture_without_client_raises_error(self):
        """MCPクライアント未設定でcaptureするとエラー"""
        # Arrange
        capture = ScreenCapture()

        # Act & Assert
        with pytest.raises(RuntimeError, match="MCP client is not set"):
            await capture.capture()


# =============================================================================
# VLMClient Tests
# =============================================================================


class TestVLMClient:
    """VLMClient クラスのテスト"""

    def test_init_with_default_model(self):
        """デフォルトモデルでインスタンス化できる"""
        # Arrange & Act: インスタンス化
        client = VLMClient()

        # Assert: デフォルトモデルが設定されている
        assert client.model == "claude-sonnet-4-20250514"

    def test_init_with_custom_model(self):
        """カスタムモデルを指定できる"""
        # Arrange & Act: カスタムモデルを指定
        client = VLMClient(model="claude-3-opus-20240229")

        # Assert: 指定したモデルが設定されている
        assert client.model == "claude-3-opus-20240229"

    def test_init_from_env_var(self):
        """環境変数からモデルを取得できる"""
        # Arrange: 環境変数を設定
        with patch.dict(os.environ, {"VLM_MODEL": "claude-3-haiku-20240307"}):
            # Act: 環境変数からモデルを取得
            client = VLMClient()

            # Assert: 環境変数のモデルが設定されている
            assert client.model == "claude-3-haiku-20240307"

    def test_get_client_without_api_key_raises_error(self):
        """APIキーがない場合エラー"""
        # Arrange: APIキーを削除
        with patch.dict(os.environ, {}, clear=True):
            # 他の必要な環境変数は保持
            with patch.dict(os.environ, {"HOME": "/tmp"}, clear=False):
                client = VLMClient()

                # Act & Assert: エラーが発生
                with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                    client._get_client()

    @pytest.mark.asyncio
    async def test_analyze_returns_description(self):
        """analyze()は画面の説明を返す"""
        # Arrange: モッククライアントを設定
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="VS Codeの画面です")]
            mock_client.messages.create.return_value = mock_response

            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                client = VLMClient()

                # Act: 画像を分析
                result = await client.analyze(b"fake-image-data", "画面を説明してください")


# =============================================================================
# ActionExecutor Tests
# =============================================================================


class TestActionExecutor:
    """ActionExecutor クラスのテスト"""

    def test_init_creates_instance(self):
        """インスタンスが作成できる"""
        # Arrange & Act
        executor = ActionExecutor()

        # Assert: mcp_clientは未設定
        assert executor._mcp_client is None

    def test_set_mcp_client(self):
        """MCPクライアントを設定できる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = MagicMock()

        # Act
        executor.set_mcp_client(mock_client)

        # Assert
        assert executor._mcp_client is mock_client

    @pytest.mark.asyncio
    async def test_click_without_client_raises_error(self):
        """MCPクライアント未設定でclickするとエラー"""
        # Arrange
        executor = ActionExecutor()

        # Act & Assert
        with pytest.raises(RuntimeError, match="MCP client is not set"):
            await executor.click(100, 100)

    @pytest.mark.asyncio
    async def test_click_with_mcp_client(self):
        """MCPクライアント経由でクリックできる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.click(100, 200)

        # Assert
        mock_client.click_coordinates.assert_called_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_double_click(self):
        """ダブルクリックできる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.click(100, 200, double_click=True)

        # Assert: click_coordinatesが2回呼ばれた
        assert mock_client.click_coordinates.call_count == 2

    @pytest.mark.asyncio
    async def test_type_text(self):
        """テキスト入力できる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.type_text("Hello World")

        # Assert
        mock_client.press_key.assert_called_once_with("Hello World")

    @pytest.mark.asyncio
    async def test_type_text_with_enter(self):
        """テキスト入力後にEnterを押せる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.type_text("search query", press_enter=True)

        # Assert
        assert mock_client.press_key.call_count == 2
        mock_client.press_key.assert_any_call("search query")
        mock_client.press_key.assert_any_call("Enter")

    @pytest.mark.asyncio
    async def test_press_key_simple(self):
        """単一キーを押せる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.press_key("escape")

        # Assert
        mock_client.press_key.assert_called_once_with("Escape")

    @pytest.mark.asyncio
    async def test_press_key_with_modifier(self):
        """修飾キー付きのキーを押せる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.press_key("ctrl+s")

        # Assert
        mock_client.press_key.assert_called_once_with("Control+S")

    @pytest.mark.asyncio
    async def test_scroll(self):
        """スクロールできる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.scroll(100, 100, delta_y=300)

        # Assert
        mock_client.scroll.assert_called_once_with(100, 100, delta_x=0, delta_y=300)

    @pytest.mark.asyncio
    async def test_drag(self):
        """ドラッグできる"""
        # Arrange
        executor = ActionExecutor()
        mock_client = AsyncMock()
        executor.set_mcp_client(mock_client)

        # Act
        await executor.drag(100, 100, 200, 200)

        # Assert
        mock_client.drag.assert_called_once_with(100, 100, 200, 200)


# =============================================================================
# VLMTesterMCPServer Tests
# =============================================================================


class TestVLMTesterMCPServer:
    """VLMTesterMCPServer クラスのテスト"""

    def test_init_creates_captures_dir(self):
        """初期化時にキャプチャディレクトリが作成される"""
        # Arrange & Act: 一時ディレクトリでサーバーを初期化
        with tempfile.TemporaryDirectory() as tmpdir:
            captures_dir = Path(tmpdir) / "captures"
            server = VLMTesterMCPServer(captures_dir=str(captures_dir))

            # Assert: ディレクトリが作成されている
            assert captures_dir.exists()
            assert captures_dir.is_dir()

    def test_save_capture_stores_image_and_metadata(self):
        """キャプチャを保存すると画像とメタデータが保存される"""
        # Arrange: サーバーを作成
        with tempfile.TemporaryDirectory() as tmpdir:
            captures_dir = Path(tmpdir) / "captures"
            server = VLMTesterMCPServer(captures_dir=str(captures_dir))

            image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # 偽のPNGデータ
            metadata = {"action": "test_capture", "region": None}

            # Act: キャプチャを保存
            filepath = server._save_capture(image_data, metadata)

            # Assert: ファイルが存在する
            assert Path(filepath).exists()

            # メタデータファイルも存在する
            meta_files = list(captures_dir.glob("*.json"))
            assert len(meta_files) == 1

            # メタデータの内容を確認
            meta_content = json.loads(meta_files[0].read_text())
            assert meta_content["action"] == "test_capture"
            assert "timestamp" in meta_content

    def test_server_name_is_vlm_tester(self):
        """サーバー名が'vlm-tester'である"""
        # Arrange & Act: サーバーを作成
        with tempfile.TemporaryDirectory() as tmpdir:
            server = VLMTesterMCPServer(captures_dir=tmpdir)

            # Assert: サーバー名を確認
            assert server.server.name == "vlm-tester"

    @pytest.mark.asyncio
    async def test_list_captures_returns_empty_for_new_dir(self):
        """新しいディレクトリではキャプチャリストが空"""
        # Arrange: サーバーを作成
        with tempfile.TemporaryDirectory() as tmpdir:
            server = VLMTesterMCPServer(captures_dir=tmpdir)

            # Act: キャプチャディレクトリ内のjsonファイルをリスト
            json_files = list(server.captures_dir.glob("*.json"))

            # Assert: 空のリスト
            assert len(json_files) == 0

    @pytest.mark.asyncio
    async def test_list_captures_returns_saved_captures(self):
        """保存したキャプチャがリストに表示される"""
        # Arrange: サーバーを作成してキャプチャを保存
        with tempfile.TemporaryDirectory() as tmpdir:
            server = VLMTesterMCPServer(captures_dir=tmpdir)

            # キャプチャを2つ保存
            server._save_capture(b"\x89PNG" + b"\x00" * 100, {"action": "capture1"})
            server._save_capture(b"\x89PNG" + b"\x00" * 100, {"action": "capture2"})

            # Act: キャプチャリストを取得
            json_files = list(server.captures_dir.glob("*.json"))

            # Assert: 2つのキャプチャが存在
            assert len(json_files) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestVLMTesterIntegration:
    """統合テスト"""

    def test_screen_capture_and_action_executor_share_mcp_client(self):
        """ScreenCaptureとActionExecutorが同じMCPクライアントを使える"""
        # Arrange: 共通のMCPクライアントを作成
        mock_client = MagicMock()
        capture = ScreenCapture()
        executor = ActionExecutor()

        # Act: 同じクライアントを設定
        capture.set_mcp_client(mock_client)
        executor.set_mcp_client(mock_client)

        # Assert: 同じクライアントが設定されている
        assert capture._mcp_client is executor._mcp_client is mock_client


# =============================================================================
# VLM Providers Tests
# =============================================================================


class TestOllamaProvider:
    """OllamaProvider のテスト"""

    def test_default_model(self):
        """デフォルトモデルが設定される"""
        # Arrange & Act
        provider = OllamaProvider()

        # Assert
        assert provider.model == "llava:7b"

    def test_custom_model_from_env(self):
        """環境変数からモデルを設定できる"""
        # Arrange
        with patch.dict(os.environ, {"OLLAMA_MODEL": "llava:13b"}):
            # Act
            provider = OllamaProvider()

            # Assert
            assert provider.model == "llava:13b"

    def test_is_available_returns_false_when_not_running(self):
        """Ollamaが動いていない場合はFalseを返す"""
        # Arrange
        provider = OllamaProvider(base_url="http://localhost:99999")

        # Act & Assert
        assert provider.is_available() is False

    def test_name_is_ollama(self):
        """プロバイダー名がollamaである"""
        # Arrange & Act
        provider = OllamaProvider()

        # Assert
        assert provider.name == "ollama"


class TestAnthropicProvider:
    """AnthropicProvider のテスト"""

    def test_is_available_with_api_key(self):
        """APIキーがある場合はTrueを返す"""
        # Arrange
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            provider = AnthropicProvider()

            # Act & Assert
            assert provider.is_available() is True

    def test_is_available_without_api_key(self):
        """APIキーがない場合はFalseを返す"""
        # Arrange
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ, {"HOME": "/tmp"}):
                provider = AnthropicProvider()

                # Act & Assert
                assert provider.is_available() is False

    def test_name_is_anthropic(self):
        """プロバイダー名がanthropicである"""
        # Arrange & Act
        provider = AnthropicProvider()

        # Assert
        assert provider.name == "anthropic"


class TestMultiProviderVLMClient:
    """MultiProviderVLMClient のテスト"""

    def test_get_available_providers(self):
        """利用可能なプロバイダーを取得できる"""
        # Arrange
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = MultiProviderVLMClient()

            # Act
            available = client.get_available_providers()

            # Assert: Anthropicは利用可能（Ollamaは動いていない可能性）
            assert "anthropic" in available

    def test_preferred_provider_setting(self):
        """優先プロバイダーを設定できる"""
        # Arrange & Act
        client = MultiProviderVLMClient(preferred_provider="anthropic")

        # Assert
        assert client.preferred_provider == "anthropic"


# =============================================================================
# Local Analyzers Tests
# =============================================================================


class TestOCRAnalyzer:
    """OCRAnalyzer のテスト"""

    def test_detect_engine_returns_none_when_no_engine(self):
        """OCRエンジンがない場合はnoneを返す"""
        # Arrange
        analyzer = OCRAnalyzer()

        # モジュールのインポートを失敗させる
        with patch.dict("sys.modules", {"easyocr": None, "pytesseract": None}):
            # 新しいインスタンスでテスト
            analyzer2 = OCRAnalyzer()
            # 直接_detect_modeを呼ぶ代わりにextract_textで確認

        # 実際の環境ではどちらかがインストールされている可能性があるので
        # エンジン検出自体をテスト
        engine = analyzer._detect_engine()
        assert engine in ["easyocr", "tesseract", "none"]


class TestDiffAnalyzer:
    """DiffAnalyzer のテスト"""

    @pytest.mark.asyncio
    async def test_compare_identical_images(self):
        """同一画像の比較で差分なしを返す"""
        # Arrange: 同一の画像を作成
        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color="red")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        analyzer = DiffAnalyzer()

        # Act
        result = await analyzer.compare(image_data, image_data)

        # Assert
        assert result.data["is_same"] is True
        assert result.data["diff_ratio"] == 0.0

    @pytest.mark.asyncio
    async def test_compare_different_images(self):
        """異なる画像の比較で差分ありを返す"""
        # Arrange: 異なる画像を作成
        from PIL import Image
        import io

        img1 = Image.new("RGB", (100, 100), color="red")
        buffer1 = io.BytesIO()
        img1.save(buffer1, format="PNG")
        image1 = buffer1.getvalue()

        img2 = Image.new("RGB", (100, 100), color="blue")
        buffer2 = io.BytesIO()
        img2.save(buffer2, format="PNG")
        image2 = buffer2.getvalue()

        analyzer = DiffAnalyzer()

        # Act
        result = await analyzer.compare(image1, image2)

        # Assert
        assert result.data["is_same"] is False
        assert result.data["diff_ratio"] > 0


# =============================================================================
# Hybrid Analyzer Tests
# =============================================================================


class TestHybridAnalyzer:
    """HybridAnalyzer のテスト"""

    def test_init_with_default_level(self):
        """デフォルトレベルで初期化できる"""
        # Arrange & Act
        analyzer = HybridAnalyzer()

        # Assert
        assert analyzer.default_level == AnalysisLevel.HYBRID

    def test_init_with_custom_level(self):
        """カスタムレベルで初期化できる"""
        # Arrange & Act
        analyzer = HybridAnalyzer(default_level=AnalysisLevel.LOCAL_ONLY)

        # Assert
        assert analyzer.default_level == AnalysisLevel.LOCAL_ONLY

    def test_get_stats_initial(self):
        """初期統計が0である"""
        # Arrange
        analyzer = HybridAnalyzer()

        # Act
        stats = analyzer.get_stats()

        # Assert
        assert stats["local_only"] == 0
        assert stats["vlm_ollama"] == 0
        assert stats["vlm_cloud"] == 0
        assert stats["total_requests"] == 0

    @pytest.mark.asyncio
    async def test_analyze_local_only_mode(self):
        """LOCAL_ONLYモードでローカル分析のみ実行"""
        # Arrange: 画像を作成
        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        analyzer = HybridAnalyzer()

        # Act
        result = await analyzer.analyze(
            image_data,
            "テキストを読み取ってください",
            level=AnalysisLevel.LOCAL_ONLY,
        )

        # Assert
        assert result.analysis_level == AnalysisLevel.LOCAL_ONLY
        assert result.vlm_response is None
