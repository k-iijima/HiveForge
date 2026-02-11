"""
ローカルVLM解析モジュールのテスト
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hiveforge.vlm.analyzer import AnalysisResult, LocalVLMAnalyzer
from hiveforge.vlm.ollama_client import OllamaClient, VLMResponse


class TestOllamaClient:
    """OllamaClientのテスト"""

    @pytest.fixture
    def client(self):
        return OllamaClient(base_url="http://localhost:11434", model="llava:7b")

    @pytest.mark.asyncio
    async def test_is_available_success(self, client):
        """Ollamaが利用可能な場合Trueを返す"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.is_available()

            # Assert
            assert result is True

    @pytest.mark.asyncio
    async def test_is_available_failure(self, client):
        """Ollamaが利用不可な場合Falseを返す（安全側フォールバック）"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            # Act
            result = await client.is_available()

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_list_models(self, client):
        """モデル一覧を取得できる"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [
                    {"name": "llava:7b"},
                    {"name": "llava:13b"},
                ]
            }
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.list_models()

            # Assert
            assert result == ["llava:7b", "llava:13b"]

    @pytest.mark.asyncio
    async def test_analyze_image_with_bytes(self, client):
        """バイトデータから画像を解析できる"""
        # Arrange
        image_bytes = b"fake image data"
        prompt = "Describe this image"

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "This is a test image",
                "prompt_eval_count": 10,
                "eval_count": 20,
                "total_duration": 1000000000,  # 1秒 in nanoseconds
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.analyze_image(image_bytes, prompt)

            # Assert
            assert isinstance(result, VLMResponse)
            assert result.response == "This is a test image"
            assert result.model == "llava:7b"
            assert result.prompt_tokens == 10
            assert result.response_tokens == 20
            assert result.total_duration_ms == 1000


class TestLocalVLMAnalyzer:
    """LocalVLMAnalyzerのテスト"""

    @pytest.fixture
    def analyzer(self):
        return LocalVLMAnalyzer(ollama_url="http://localhost:11434", model="llava:7b")

    @pytest.mark.asyncio
    async def test_is_ready_when_model_available(self, analyzer):
        """モデルが利用可能な場合Trueを返す"""
        # Arrange
        analyzer.client.is_available = AsyncMock(return_value=True)
        analyzer.client.list_models = AsyncMock(return_value=["llava:7b", "llava:13b"])

        # Act
        result = await analyzer.is_ready()

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_is_ready_when_ollama_not_running(self, analyzer):
        """Ollamaが起動していない場合Falseを返す"""
        # Arrange
        analyzer.client.is_available = AsyncMock(return_value=False)

        # Act
        result = await analyzer.is_ready()

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_is_ready_when_model_not_installed(self, analyzer):
        """モデルがインストールされていない場合Falseを返す"""
        # Arrange
        analyzer.client.is_available = AsyncMock(return_value=True)
        analyzer.client.list_models = AsyncMock(return_value=["other-model"])

        # Act
        result = await analyzer.is_ready()

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_analyze_extracts_ui_elements(self, analyzer):
        """解析結果からUI要素を抽出する"""
        # Arrange
        mock_response = VLMResponse(
            response="The image shows a VS Code interface with a sidebar on the left, "
            "an editor area in the center, and a terminal panel at the bottom.",
            model="llava:7b",
            prompt_tokens=10,
            response_tokens=30,
            total_duration_ms=500,
        )
        analyzer.client.analyze_screenshot = AsyncMock(return_value=mock_response)

        # Act
        result = await analyzer.analyze(b"fake image")

        # Assert
        assert isinstance(result, AnalysisResult)
        assert "sidebar" in result.elements_found
        assert "editor" in result.elements_found
        assert "terminal" in result.elements_found

    def test_extract_elements(self, analyzer):
        """UI要素キーワードを正しく抽出する"""
        # Arrange
        text = "The sidebar contains the explorer panel. The editor shows code. The status bar is at the bottom."

        # Act
        elements = analyzer._extract_elements(text)

        # Assert
        assert "sidebar" in elements
        assert "explorer" in elements
        assert "editor" in elements
        assert "status bar" in elements


class TestVLMResponse:
    """VLMResponseモデルのテスト"""

    def test_create_valid_response(self):
        """有効なレスポンスを作成できる"""
        # Arrange & Act
        response = VLMResponse(
            response="Test response",
            model="llava:7b",
            prompt_tokens=10,
            response_tokens=20,
            total_duration_ms=1000,
        )

        # Assert
        assert response.response == "Test response"
        assert response.model == "llava:7b"

    def test_default_values(self):
        """デフォルト値が設定される"""
        # Arrange & Act
        response = VLMResponse(response="Test", model="llava:7b")

        # Assert
        assert response.prompt_tokens == 0
        assert response.response_tokens == 0
        assert response.total_duration_ms == 0


class TestResolveImageToBase64:
    """H-07: _resolve_image_to_base64 validates input properly"""

    def test_path_object(self, tmp_path):
        """Path object is read and base64-encoded"""
        # Arrange
        img = tmp_path / "img.png"
        img.write_bytes(b"PNG_DATA")

        # Act
        result = OllamaClient._resolve_image_to_base64(img)

        # Assert
        assert result == base64.b64encode(b"PNG_DATA").decode()

    def test_string_file_path(self, tmp_path):
        """String pointing to existing file is read and encoded"""
        # Arrange
        img = tmp_path / "img.png"
        img.write_bytes(b"PNG_DATA_2")

        # Act
        result = OllamaClient._resolve_image_to_base64(str(img))

        # Assert
        assert result == base64.b64encode(b"PNG_DATA_2").decode()

    def test_bytes_input(self):
        """Raw bytes are base64-encoded"""
        # Arrange
        raw = b"raw image bytes"

        # Act
        result = OllamaClient._resolve_image_to_base64(raw)

        # Assert
        assert result == base64.b64encode(raw).decode()

    def test_valid_base64_string(self):
        """Valid base64 string (non-file) is accepted as-is"""
        # Arrange
        image_b64 = base64.b64encode(b"fake image data for test").decode()

        # Act
        result = OllamaClient._resolve_image_to_base64(image_b64)

        # Assert
        assert result == image_b64

    def test_invalid_string_raises_value_error(self):
        """Non-file, non-base64 string raises ValueError"""
        # Arrange
        garbage = "not_a_file_and_not_base64!!!"

        # Act & Assert
        with pytest.raises(ValueError, match="neither an existing file path"):
            OllamaClient._resolve_image_to_base64(garbage)

    def test_empty_string_raises_value_error(self):
        """Empty string raises ValueError"""
        with pytest.raises(ValueError, match="neither an existing file path"):
            OllamaClient._resolve_image_to_base64("")


class TestOllamaClientExtended:
    """OllamaClient 拡張テスト"""

    @pytest.fixture
    def client(self):
        return OllamaClient(base_url="http://localhost:11434", model="llava:7b")

    @pytest.mark.asyncio
    async def test_list_models_empty(self, client):
        """モデルがない場合空のリストを返す"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"models": []}
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.list_models()

            # Assert
            assert result == []

    @pytest.mark.asyncio
    async def test_list_models_exception_raises(self, client):
        """ネットワークエラー時に例外がそのまま伝搬される"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Network error")
            )

            # Act & Assert: httpx.HTTPError が伝搬
            with pytest.raises(httpx.HTTPError):
                await client.list_models()

    @pytest.mark.asyncio
    async def test_pull_model_success(self, client):
        """モデルダウンロード成功"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.pull_model()

            # Assert
            assert result is True

    @pytest.mark.asyncio
    async def test_pull_model_failure(self, client):
        """モデルダウンロード失敗"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.pull_model()

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_pull_model_exception_raises(self, client):
        """モデルダウンロード時のネットワークエラーが伝搬される"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Timeout")
            )

            # Act & Assert: httpx.HTTPError が伝搬
            with pytest.raises(httpx.HTTPError):
                await client.pull_model()

    @pytest.mark.asyncio
    async def test_pull_model_custom_name(self, client):
        """カスタムモデル名でダウンロード"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.pull_model("custom:model")

            # Assert
            assert result is True
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            assert call_args.kwargs["json"]["name"] == "custom:model"

    @pytest.mark.asyncio
    async def test_analyze_image_with_file_path(self, client, tmp_path):
        """ファイルパスから画像を解析できる"""
        # Arrange
        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"fake image data")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "File path test",
                "prompt_eval_count": 5,
                "eval_count": 10,
                "total_duration": 500000000,
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.analyze_image(image_path, "Describe")

            # Assert
            assert result.response == "File path test"

    @pytest.mark.asyncio
    async def test_analyze_image_with_string_path(self, client, tmp_path):
        """文字列パスから画像を解析できる"""
        # Arrange
        image_path = tmp_path / "test2.png"
        image_path.write_bytes(b"fake image data 2")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "String path test",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.analyze_image(str(image_path), "Describe")

            # Assert
            assert result.response == "String path test"

    @pytest.mark.asyncio
    async def test_analyze_image_with_base64_string(self, client):
        """Base64文字列から画像を解析できる"""
        # Arrange
        image_b64 = base64.b64encode(b"fake image").decode()

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "Base64 test",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            result = await client.analyze_image(image_b64, "Describe")

            # Assert
            assert result.response == "Base64 test"

    @pytest.mark.asyncio
    async def test_analyze_image_with_custom_model(self, client):
        """カスタムモデルで解析できる"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "Custom model test",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            await client.analyze_image(b"image", "prompt", model="custom:7b")

            # Assert
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            assert call_args.kwargs["json"]["model"] == "custom:7b"

    @pytest.mark.asyncio
    async def test_analyze_screenshot(self, client):
        """スクリーンショット解析用のプロンプトで解析できる"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "Screenshot analysis result",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            await client.analyze_screenshot(b"screenshot", context="VS Code editor")

            # Assert
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            prompt = call_args.kwargs["json"]["prompt"]
            assert "UI elements" in prompt
            assert "VS Code editor" in prompt

    @pytest.mark.asyncio
    async def test_analyze_screenshot_no_context(self, client):
        """コンテキストなしでスクリーンショット解析できる"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "No context result",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            # Act
            await client.analyze_screenshot(b"screenshot")

            # Assert
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            prompt = call_args.kwargs["json"]["prompt"]
            assert "Additional context" not in prompt


class TestLocalVLMAnalyzerExtended:
    """LocalVLMAnalyzer 拡張テスト"""

    @pytest.fixture
    def analyzer(self):
        return LocalVLMAnalyzer(ollama_url="http://localhost:11434", model="llava:7b")

    @pytest.mark.asyncio
    async def test_setup_success(self, analyzer):
        """セットアップ成功（モデルあり）"""
        # Arrange
        analyzer.client.is_available = AsyncMock(return_value=True)
        analyzer.client.list_models = AsyncMock(return_value=["llava:7b"])

        # Act
        result = await analyzer.setup()

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_setup_downloads_model(self, analyzer):
        """セットアップ時にモデルをダウンロードする"""
        # Arrange
        analyzer.client.is_available = AsyncMock(return_value=True)
        analyzer.client.list_models = AsyncMock(return_value=[])
        analyzer.client.pull_model = AsyncMock(return_value=True)

        # Act
        result = await analyzer.setup()

        # Assert
        assert result is True
        analyzer.client.pull_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_ollama_not_running(self, analyzer):
        """Ollamaが起動していない場合RuntimeError"""
        # Arrange
        analyzer.client.is_available = AsyncMock(return_value=False)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Ollama is not running"):
            await analyzer.setup()

    @pytest.mark.asyncio
    async def test_analyze_with_custom_prompt(self, analyzer):
        """カスタムプロンプトで解析できる"""
        # Arrange
        mock_response = VLMResponse(
            response="Custom prompt result",
            model="llava:7b",
        )
        analyzer.client.analyze_image = AsyncMock(return_value=mock_response)

        # Act
        await analyzer.analyze(b"image", prompt="Custom prompt")

        # Assert
        analyzer.client.analyze_image.assert_called_once()
        call_args = analyzer.client.analyze_image.call_args
        assert call_args.args[1] == "Custom prompt"

    @pytest.mark.asyncio
    async def test_analyze_with_file_path(self, analyzer, tmp_path):
        """ファイルパスで解析するとscreenshot_pathが設定される"""
        # Arrange
        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"test image")

        mock_response = VLMResponse(
            response="Path test",
            model="llava:7b",
        )
        analyzer.client.analyze_screenshot = AsyncMock(return_value=mock_response)

        # Act
        result = await analyzer.analyze(str(image_path))

        # Assert
        assert result.screenshot_path == str(image_path)

    @pytest.mark.asyncio
    async def test_analyze_with_bytes(self, analyzer):
        """バイトデータで解析するとscreenshot_pathがNone"""
        # Arrange
        mock_response = VLMResponse(
            response="Bytes test",
            model="llava:7b",
        )
        analyzer.client.analyze_screenshot = AsyncMock(return_value=mock_response)

        # Act
        result = await analyzer.analyze(b"image bytes")

        # Assert
        assert result.screenshot_path is None

    @pytest.mark.asyncio
    async def test_compare_screenshots(self, analyzer):
        """スクリーンショット比較ができる"""
        # Arrange
        mock_response = VLMResponse(
            response="Analysis before",
            model="llava:7b",
        )
        mock_diff_response = VLMResponse(
            response="The button changed color",
            model="llava:7b",
        )
        analyzer.client.analyze_screenshot = AsyncMock(return_value=mock_response)
        analyzer.client.analyze_image = AsyncMock(return_value=mock_diff_response)

        # Act
        result = await analyzer.compare_screenshots(b"before", b"after")

        # Assert
        assert "changed" in result

    def test_extract_elements_all_keywords(self, analyzer):
        """全てのキーワードを抽出できる"""
        # Arrange
        text = """
        The sidebar is on the left with explorer and source control.
        The editor area shows code with a toolbar at the top.
        The status bar is at the bottom.
        The activity bar has extensions and debug icons.
        The terminal, output, and problems panels are visible.
        There are notifications, a search bar, menu, and several tabs.
        """

        # Act
        elements = analyzer._extract_elements(text)

        # Assert
        expected = [
            "sidebar",
            "editor",
            "toolbar",
            "status bar",
            "activity bar",
            "explorer",
            "terminal",
            "output",
            "problems",
            "debug",
            "extensions",
            "search",
            "source control",
            "notifications",
        ]
        for elem in expected:
            assert elem in elements, f"{elem} should be extracted"

    def test_extract_elements_no_match(self, analyzer):
        """マッチしない場合空のリスト"""
        # Arrange
        text = "This is a random text with no UI elements mentioned."

        # Act
        elements = analyzer._extract_elements(text)

        # Assert
        assert elements == []


class TestAnalyzeWithLocalVLM:
    """analyze_with_local_vlm ユーティリティ関数のテスト"""

    @pytest.mark.asyncio
    async def test_analyze_with_local_vlm(self):
        """ワンショット解析関数が動作する"""
        # Arrange
        from hiveforge.vlm.analyzer import analyze_with_local_vlm

        with patch.object(LocalVLMAnalyzer, "analyze") as mock_analyze:
            mock_result = AnalysisResult(
                analysis="Test result",
                model="llava:7b",
            )
            mock_analyze.return_value = mock_result

            # Act
            result = await analyze_with_local_vlm(b"image")

            # Assert
            mock_analyze.assert_called_once()
            assert result == mock_result
