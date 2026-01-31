"""
ローカルVLM解析モジュールのテスト
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import base64

from hiveforge.vlm.ollama_client import OllamaClient, VLMResponse
from hiveforge.vlm.analyzer import LocalVLMAnalyzer, AnalysisResult


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
        """Ollamaが利用不可な場合Falseを返す"""
        # Arrange
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection refused")
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
