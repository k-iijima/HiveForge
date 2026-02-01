"""Colony MCP ツールのテスト

GitHub Issue #10: P1-09: Colony MCP ツール実装
"""

import pytest


class TestColonyMCPToolDefinitions:
    """Colony MCPツール定義のテスト"""

    def test_create_colony_tool_exists(self):
        """create_colonyツールが存在する"""
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]
        assert "create_colony" in tool_names

    def test_list_colonies_tool_exists(self):
        """list_coloniesツールが存在する"""
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]
        assert "list_colonies" in tool_names

    def test_start_colony_tool_exists(self):
        """start_colonyツールが存在する"""
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]
        assert "start_colony" in tool_names

    def test_complete_colony_tool_exists(self):
        """complete_colonyツールが存在する"""
        from hiveforge.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]
        assert "complete_colony" in tool_names


class TestColonyMCPHandlers:
    """Colony MCPハンドラーのテスト"""

    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        """テスト用MCPサーバー"""
        from hiveforge.mcp_server.server import HiveForgeMCPServer

        server = HiveForgeMCPServer()
        server._handle_create_colony = server._colony_handlers.handle_create_colony
        server._handle_list_colonies = server._colony_handlers.handle_list_colonies
        server._handle_start_colony = server._colony_handlers.handle_start_colony
        server._handle_complete_colony = server._colony_handlers.handle_complete_colony
        return server

    @pytest.fixture
    async def hive_id(self, mcp_server):
        """テスト用Hive"""
        result = await mcp_server._hive_handlers.handle_create_hive({"name": "TestHive"})
        return result["hive_id"]

    @pytest.mark.asyncio
    async def test_create_colony(self, mcp_server, hive_id):
        """Colonyを作成できる"""
        result = await mcp_server._handle_create_colony(
            {
                "hive_id": hive_id,
                "name": "TestColony",
                "goal": "テスト目標",
            }
        )
        assert "colony_id" in result
        assert result["name"] == "TestColony"

    @pytest.mark.asyncio
    async def test_create_colony_hive_not_found(self, mcp_server):
        """存在しないHiveにはColonyを作成できない"""
        result = await mcp_server._handle_create_colony(
            {
                "hive_id": "nonexistent",
                "name": "TestColony",
            }
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_colonies(self, mcp_server, hive_id):
        """Colony一覧を取得できる"""
        await mcp_server._handle_create_colony({"hive_id": hive_id, "name": "Colony1"})
        await mcp_server._handle_create_colony({"hive_id": hive_id, "name": "Colony2"})

        result = await mcp_server._handle_list_colonies({"hive_id": hive_id})
        assert "colonies" in result
        assert len(result["colonies"]) >= 2

    @pytest.mark.asyncio
    async def test_start_colony(self, mcp_server, hive_id):
        """Colonyを開始できる"""
        create_result = await mcp_server._handle_create_colony(
            {
                "hive_id": hive_id,
                "name": "StartTest",
            }
        )
        colony_id = create_result["colony_id"]

        result = await mcp_server._handle_start_colony({"colony_id": colony_id})
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_complete_colony(self, mcp_server, hive_id):
        """Colonyを完了できる"""
        create_result = await mcp_server._handle_create_colony(
            {
                "hive_id": hive_id,
                "name": "CompleteTest",
            }
        )
        colony_id = create_result["colony_id"]
        await mcp_server._handle_start_colony({"colony_id": colony_id})

        result = await mcp_server._handle_complete_colony({"colony_id": colony_id})
        assert result["status"] == "completed"
