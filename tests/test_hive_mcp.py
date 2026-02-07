"""Hive MCP ツールのテスト

GitHub Issue #9: P1-08: Hive MCP ツール実装
"""

from unittest.mock import MagicMock, patch

import pytest


class TestHiveMCPToolDefinitions:
    """Hive MCPツール定義のテスト"""

    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        """テスト用MCPサーバー"""
        from hiveforge.mcp_server.server import HiveForgeMCPServer

        with patch("hiveforge.mcp_server.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = tmp_path / "Vault"
            mock_settings.return_value = mock_s

            server = HiveForgeMCPServer()
            # ハンドラを直接アクセス可能にする
            server._handle_create_hive = server._hive_handlers.handle_create_hive
            server._handle_list_hives = server._hive_handlers.handle_list_hives
            server._handle_get_hive = server._hive_handlers.handle_get_hive
            server._handle_close_hive = server._hive_handlers.handle_close_hive
            yield server

    def test_create_hive_tool_exists(self, mcp_server):
        """create_hiveツールが存在する"""
        # Act
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        # Assert
        assert "create_hive" in tool_names

    def test_list_hives_tool_exists(self, mcp_server):
        """list_hivesツールが存在する"""
        # Act
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        # Assert
        assert "list_hives" in tool_names

    def test_get_hive_tool_exists(self, mcp_server):
        """get_hiveツールが存在する"""
        # Act
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        # Assert
        assert "get_hive" in tool_names

    def test_close_hive_tool_exists(self, mcp_server):
        """close_hiveツールが存在する"""
        # Act
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        # Assert
        assert "close_hive" in tool_names


class TestHiveMCPHandlers:
    """Hive MCPハンドラーのテスト"""

    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        """テスト用MCPサーバー"""
        from hiveforge.mcp_server.server import HiveForgeMCPServer

        with patch("hiveforge.mcp_server.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = tmp_path / "Vault"
            mock_settings.return_value = mock_s

            server = HiveForgeMCPServer()
            server._handle_create_hive = server._hive_handlers.handle_create_hive
            server._handle_list_hives = server._hive_handlers.handle_list_hives
            server._handle_get_hive = server._hive_handlers.handle_get_hive
            server._handle_close_hive = server._hive_handlers.handle_close_hive
            yield server

    @pytest.mark.asyncio
    async def test_create_hive(self, mcp_server):
        """Hiveを作成できる"""
        # Act
        result = await mcp_server._handle_create_hive(
            {
                "name": "TestHive",
                "description": "テスト用Hive",
            }
        )

        # Assert
        assert "hive_id" in result
        assert result["name"] == "TestHive"
        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_list_hives_empty(self, mcp_server):
        """Hive一覧が空の場合は空リストを返す"""
        # Act
        result = await mcp_server._handle_list_hives({})

        # Assert
        assert "hives" in result
        assert isinstance(result["hives"], list)

    @pytest.mark.asyncio
    async def test_list_hives_after_create(self, mcp_server):
        """Hive作成後に一覧に表示される"""
        # Arrange
        await mcp_server._handle_create_hive({"name": "Hive1"})
        await mcp_server._handle_create_hive({"name": "Hive2"})

        # Act
        result = await mcp_server._handle_list_hives({})

        # Assert
        assert len(result["hives"]) >= 2

    @pytest.mark.asyncio
    async def test_get_hive(self, mcp_server):
        """Hive詳細を取得できる"""
        # Arrange
        create_result = await mcp_server._handle_create_hive({"name": "GetTest"})
        hive_id = create_result["hive_id"]

        # Act
        result = await mcp_server._handle_get_hive({"hive_id": hive_id})

        # Assert
        assert result["hive_id"] == hive_id
        assert result["name"] == "GetTest"

    @pytest.mark.asyncio
    async def test_get_hive_not_found(self, mcp_server):
        """存在しないHiveはエラーを返す"""
        # Act
        result = await mcp_server._handle_get_hive({"hive_id": "nonexistent"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_close_hive(self, mcp_server):
        """Hiveを終了できる"""
        # Arrange
        create_result = await mcp_server._handle_create_hive({"name": "CloseTest"})
        hive_id = create_result["hive_id"]

        # Act
        result = await mcp_server._handle_close_hive({"hive_id": hive_id})

        # Assert
        assert result["hive_id"] == hive_id
        assert result["status"] == "closed"

    @pytest.mark.asyncio
    async def test_close_hive_not_found(self, mcp_server):
        """存在しないHiveの終了はエラーを返す"""
        # Act
        result = await mcp_server._handle_close_hive({"hive_id": "nonexistent"})

        # Assert
        assert "error" in result
