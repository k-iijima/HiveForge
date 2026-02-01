"""Beekeeper MCPサーバーのテスト"""

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.beekeeper.server import BeekeeperMCPServer
from hiveforge.beekeeper.session import SessionState


@pytest.fixture
def ar(tmp_path):
    """テスト用Akashic Record"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def beekeeper(ar):
    """テスト用Beekeeper"""
    return BeekeeperMCPServer(ar=ar)


class TestBeekeeperMCPServer:
    """Beekeeper MCPサーバーの基本テスト"""

    def test_initialization(self, beekeeper):
        """Beekeeperが正しく初期化される"""
        # Assert
        assert beekeeper.ar is not None
        assert beekeeper.session_manager is not None
        assert beekeeper.current_session is None

    def test_get_tool_definitions(self, beekeeper):
        """ツール定義が正しく取得できる"""
        # Act
        tools = beekeeper.get_tool_definitions()

        # Assert
        tool_names = [t["name"] for t in tools]
        assert "send_message" in tool_names
        assert "get_status" in tool_names
        assert "create_hive" in tool_names
        assert "create_colony" in tool_names
        assert "list_hives" in tool_names
        assert "list_colonies" in tool_names
        assert "approve" in tool_names
        assert "reject" in tool_names
        assert "emergency_stop" in tool_names


class TestSendMessage:
    """send_messageハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_send_message_creates_session(self, beekeeper):
        """セッションがなければ作成される"""
        # Arrange
        assert beekeeper.current_session is None

        # Act - LLMなしでも基本的なセッション作成は動作する
        # (LLMがないとエラーになるが、セッションは作成される)
        try:
            await beekeeper.handle_send_message({"message": "Hello"})
        except Exception:
            pass

        # Assert - セッションが作成された
        assert beekeeper.current_session is not None


class TestGetStatus:
    """get_statusハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_get_status_no_session(self, beekeeper):
        """セッションなしでステータス取得"""
        # Act
        result = await beekeeper.handle_get_status({})

        # Assert
        assert result["status"] == "success"
        assert result["session"] is None

    @pytest.mark.asyncio
    async def test_get_status_with_session(self, beekeeper):
        """セッションありでステータス取得"""
        # Arrange
        beekeeper.current_session = beekeeper.session_manager.create_session()
        beekeeper.current_session.activate("hive-1")

        # Act
        result = await beekeeper.handle_get_status({})

        # Assert
        assert result["status"] == "success"
        assert result["session"] is not None
        assert result["session"]["hive_id"] == "hive-1"


class TestCreateHive:
    """create_hiveハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_create_hive_success(self, beekeeper):
        """Hive作成成功"""
        # Act
        result = await beekeeper.handle_create_hive(
            {
                "name": "MyProject",
                "goal": "Build awesome app",
            }
        )

        # Assert
        assert result["status"] == "created"
        assert result["hive_id"] is not None
        assert result["name"] == "MyProject"
        assert result["goal"] == "Build awesome app"

    @pytest.mark.asyncio
    async def test_create_hive_activates_session(self, beekeeper):
        """Hive作成時にセッションがアクティブ化される"""
        # Act
        result = await beekeeper.handle_create_hive(
            {
                "name": "MyProject",
                "goal": "Build awesome app",
            }
        )

        # Assert
        assert beekeeper.current_session is not None
        assert beekeeper.current_session.hive_id == result["hive_id"]
        assert beekeeper.current_session.state == SessionState.ACTIVE


class TestCreateColony:
    """create_colonyハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_create_colony_success(self, beekeeper):
        """Colony作成成功"""
        # Arrange
        await beekeeper.handle_create_hive({"name": "Test", "goal": "Test"})

        # Act
        result = await beekeeper.handle_create_colony(
            {
                "hive_id": beekeeper.current_session.hive_id,
                "name": "Frontend",
                "domain": "UI/UX implementation",
            }
        )

        # Assert
        assert result["status"] == "created"
        assert result["colony_id"] is not None
        assert result["name"] == "Frontend"
        assert result["domain"] == "UI/UX implementation"

    @pytest.mark.asyncio
    async def test_create_colony_adds_to_session(self, beekeeper):
        """Colony作成時にセッションに追加される"""
        # Arrange
        await beekeeper.handle_create_hive({"name": "Test", "goal": "Test"})

        # Act
        result = await beekeeper.handle_create_colony(
            {
                "hive_id": beekeeper.current_session.hive_id,
                "name": "API",
                "domain": "Backend API",
            }
        )

        # Assert
        assert result["colony_id"] in beekeeper.current_session.active_colonies


class TestListHives:
    """list_hivesハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_list_hives_empty(self, beekeeper):
        """Hiveなしで一覧取得"""
        # Act
        result = await beekeeper.handle_list_hives({})

        # Assert
        assert result["status"] == "success"
        assert result["hives"] == []


class TestListColonies:
    """list_coloniesハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_list_colonies_empty(self, beekeeper):
        """Colonyなしで一覧取得"""
        # Act
        result = await beekeeper.handle_list_colonies({"hive_id": "hive-1"})

        # Assert
        assert result["status"] == "success"
        assert result["colonies"] == []


class TestApproveReject:
    """approve/rejectハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_approve(self, beekeeper):
        """承認"""
        # Act
        result = await beekeeper.handle_approve(
            {
                "request_id": "req-1",
                "comment": "LGTM",
            }
        )

        # Assert
        assert result["status"] == "approved"
        assert result["request_id"] == "req-1"

    @pytest.mark.asyncio
    async def test_reject(self, beekeeper):
        """拒否"""
        # Act
        result = await beekeeper.handle_reject(
            {
                "request_id": "req-1",
                "reason": "Too risky",
            }
        )

        # Assert
        assert result["status"] == "rejected"
        assert result["reason"] == "Too risky"


class TestEmergencyStop:
    """emergency_stopハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_emergency_stop_all(self, beekeeper):
        """全停止"""
        # Act
        result = await beekeeper.handle_emergency_stop(
            {
                "reason": "Critical error detected",
            }
        )

        # Assert
        assert result["status"] == "stopped"
        assert result["reason"] == "Critical error detected"
        assert result["scope"] == "all"

    @pytest.mark.asyncio
    async def test_emergency_stop_colony(self, beekeeper):
        """Colony停止"""
        # Act
        result = await beekeeper.handle_emergency_stop(
            {
                "reason": "Colony malfunction",
                "scope": "colony",
                "target_id": "colony-1",
            }
        )

        # Assert
        assert result["status"] == "stopped"
        assert result["scope"] == "colony"
        assert result["target_id"] == "colony-1"


class TestDispatchTool:
    """dispatch_toolのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_get_status(self, beekeeper):
        """get_statusがディスパッチされる"""
        result = await beekeeper.dispatch_tool("get_status", {})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self, beekeeper):
        """未知のツールはエラー"""
        result = await beekeeper.dispatch_tool("unknown_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]


class TestClose:
    """closeのテスト"""

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, beekeeper):
        """closeでリソースが解放される"""
        # 何も初期化されていない状態でcloseしてもエラーにならない
        await beekeeper.close()

        assert beekeeper._llm_client is None
        assert beekeeper._agent_runner is None

    @pytest.mark.asyncio
    async def test_close_releases_queens(self, beekeeper):
        """closeでQueen Beeも解放される"""
        # Arrange: Queen Beeを作成
        from hiveforge.queen_bee.server import QueenBeeMCPServer

        queen = QueenBeeMCPServer(colony_id="colony-1", ar=beekeeper.ar)
        beekeeper._queens["colony-1"] = queen

        # Act
        await beekeeper.close()

        # Assert
        assert len(beekeeper._queens) == 0


class TestDelegateToQueen:
    """Queen Beeへの委譲テスト"""

    @pytest.mark.asyncio
    async def test_delegate_creates_queen(self, beekeeper):
        """委譲時にQueen Beeが作成される"""
        # Act
        result = await beekeeper._delegate_to_queen(
            colony_id="colony-1",
            task="Test task",
            context={},
        )

        # Assert
        assert "colony-1" in beekeeper._queens
        assert "タスク完了" in result or "タスク失敗" in result

    @pytest.mark.asyncio
    async def test_delegate_reuses_queen(self, beekeeper):
        """同じColonyへの委譲は既存Queenを再利用"""
        # Arrange
        await beekeeper._delegate_to_queen("colony-1", "First task")
        first_queen = beekeeper._queens["colony-1"]

        # Act
        await beekeeper._delegate_to_queen("colony-1", "Second task")
        second_queen = beekeeper._queens["colony-1"]

        # Assert
        assert first_queen is second_queen

    @pytest.mark.asyncio
    async def test_delegate_adds_colony_to_session(self, beekeeper):
        """委譲時にセッションにColonyが追加される"""
        # Arrange
        beekeeper.current_session = beekeeper.session_manager.create_session()

        # Act
        await beekeeper._delegate_to_queen("colony-1", "Task")

        # Assert
        assert "colony-1" in beekeeper.current_session.active_colonies
