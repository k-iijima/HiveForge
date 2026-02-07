"""Beekeeper MCPサーバーのテスト"""

import pytest

from hiveforge.beekeeper.server import BeekeeperMCPServer
from hiveforge.beekeeper.session import SessionState
from hiveforge.core import AkashicRecord


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

    @pytest.mark.asyncio
    async def test_get_status_returns_hive_data(self, beekeeper):
        """作成済みHiveの情報がステータスに含まれる"""
        # Arrange: Hiveを作成
        hive_result = await beekeeper.handle_create_hive({"name": "StatusTest", "goal": "Testing"})
        hive_id = hive_result["hive_id"]

        # Act
        result = await beekeeper.handle_get_status({})

        # Assert
        assert result["status"] == "success"
        assert len(result["hives"]) >= 1
        hive_names = {h["name"] for h in result["hives"]}
        assert "StatusTest" in hive_names

    @pytest.mark.asyncio
    async def test_get_status_specific_hive(self, beekeeper):
        """特定Hiveのステータスを取得"""
        # Arrange: Hiveを作成
        hive_result = await beekeeper.handle_create_hive(
            {"name": "SpecificHive", "goal": "Specific"}
        )
        hive_id = hive_result["hive_id"]

        # Act
        result = await beekeeper.handle_get_status({"hive_id": hive_id})

        # Assert
        assert result["status"] == "success"
        assert len(result["hives"]) == 1
        assert result["hives"][0]["name"] == "SpecificHive"

    @pytest.mark.asyncio
    async def test_get_status_includes_colonies(self, beekeeper):
        """ステータスにColony情報が含まれる"""
        # Arrange: Hive + Colony作成
        hive_result = await beekeeper.handle_create_hive({"name": "WithColonies", "goal": "Test"})
        hive_id = hive_result["hive_id"]
        await beekeeper.handle_create_colony(
            {
                "hive_id": hive_id,
                "name": "Col1",
                "domain": "Domain1",
            }
        )

        # Act
        result = await beekeeper.handle_get_status({"hive_id": hive_id, "include_colonies": True})

        # Assert
        assert result["colonies"] is not None
        assert len(result["colonies"]) == 1


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

    @pytest.mark.asyncio
    async def test_create_hive_persists_event(self, beekeeper):
        """Hive作成時にHiveStoreにイベントが永続化される"""
        # Act
        result = await beekeeper.handle_create_hive({"name": "PersistTest", "goal": "Persist"})
        hive_id = result["hive_id"]

        # Assert: HiveStoreにイベントが記録されている
        events = list(beekeeper.hive_store.replay(hive_id))
        assert len(events) == 1
        assert events[0].type.value == "hive.created"
        assert events[0].payload["name"] == "PersistTest"


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

    @pytest.mark.asyncio
    async def test_create_colony_hive_not_found(self, beekeeper):
        """存在しないHiveにColony作成するとエラー"""
        # Act
        result = await beekeeper.handle_create_colony(
            {"hive_id": "nonexistent", "name": "Col", "domain": "dom"}
        )

        # Assert
        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_colony_persists_event(self, beekeeper):
        """Colony作成時にイベントがHiveStoreに永続化される"""
        # Arrange
        hive_result = await beekeeper.handle_create_hive({"name": "Test", "goal": "Test"})
        hive_id = hive_result["hive_id"]

        # Act
        await beekeeper.handle_create_colony(
            {"hive_id": hive_id, "name": "Workers", "domain": "Work"}
        )

        # Assert: HiveStoreにcolony.createdイベントが追加されている
        events = list(beekeeper.hive_store.replay(hive_id))
        event_types = [e.type.value for e in events]
        assert "colony.created" in event_types


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

    @pytest.mark.asyncio
    async def test_list_hives_returns_created_hives(self, beekeeper):
        """作成したHiveが一覧に表示される"""
        # Arrange: Hiveを2つ作成
        await beekeeper.handle_create_hive({"name": "Hive1", "goal": "Goal1"})
        await beekeeper.handle_create_hive({"name": "Hive2", "goal": "Goal2"})

        # Act
        result = await beekeeper.handle_list_hives({})

        # Assert
        assert result["status"] == "success"
        assert len(result["hives"]) == 2
        names = {h["name"] for h in result["hives"]}
        assert names == {"Hive1", "Hive2"}


class TestListColonies:
    """list_coloniesハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_list_colonies_hive_not_found(self, beekeeper):
        """存在しないHiveのColony一覧はエラー"""
        # Act
        result = await beekeeper.handle_list_colonies({"hive_id": "hive-1"})

        # Assert
        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_list_colonies_empty(self, beekeeper):
        """HiveにColonyがない場合は空リスト"""
        # Arrange: Hiveを作成
        hive_result = await beekeeper.handle_create_hive({"name": "Test", "goal": "Test"})
        hive_id = hive_result["hive_id"]

        # Act
        result = await beekeeper.handle_list_colonies({"hive_id": hive_id})

        # Assert
        assert result["status"] == "success"
        assert result["colonies"] == []

    @pytest.mark.asyncio
    async def test_list_colonies_returns_created_colonies(self, beekeeper):
        """作成したColonyが一覧に表示される"""
        # Arrange: Hive + Colonyを作成
        hive_result = await beekeeper.handle_create_hive({"name": "Test", "goal": "Test"})
        hive_id = hive_result["hive_id"]
        await beekeeper.handle_create_colony(
            {
                "hive_id": hive_id,
                "name": "Frontend",
                "domain": "UI",
            }
        )
        await beekeeper.handle_create_colony(
            {
                "hive_id": hive_id,
                "name": "Backend",
                "domain": "API",
            }
        )

        # Act
        result = await beekeeper.handle_list_colonies({"hive_id": hive_id})

        # Assert
        assert result["status"] == "success"
        assert len(result["colonies"]) == 2
        names = {c["name"] for c in result["colonies"]}
        assert names == {"Frontend", "Backend"}


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
    async def test_approve_persists_event(self, beekeeper):
        """承認時にRequirementApprovedイベントがARに永続化される"""
        # Act
        await beekeeper.handle_approve({"request_id": "req-1", "comment": "OK"})

        # Assert: ARにイベントが記録されている
        events = list(beekeeper.ar.replay("req-1"))
        assert len(events) == 1
        assert events[0].type.value == "requirement.approved"
        assert events[0].payload["comment"] == "OK"

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

    @pytest.mark.asyncio
    async def test_reject_persists_event(self, beekeeper):
        """拒否時にRequirementRejectedイベントがARに永続化される"""
        # Act
        await beekeeper.handle_reject({"request_id": "req-2", "reason": "Unsafe"})

        # Assert: ARにイベントが記録されている
        events = list(beekeeper.ar.replay("req-2"))
        assert len(events) == 1
        assert events[0].type.value == "requirement.rejected"
        assert events[0].payload["reason"] == "Unsafe"


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

    @pytest.mark.asyncio
    async def test_emergency_stop_persists_event(self, beekeeper):
        """緊急停止時にEmergencyStopイベントがARに永続化される"""
        # Act
        await beekeeper.handle_emergency_stop({"reason": "Critical"})

        # Assert: ARにイベントが記録されている
        events = list(beekeeper.ar.replay("system"))
        assert len(events) == 1
        assert events[0].type.value == "system.emergency_stop"
        assert events[0].payload["reason"] == "Critical"

    @pytest.mark.asyncio
    async def test_emergency_stop_suspends_session(self, beekeeper):
        """緊急停止でセッションが一時停止される"""
        # Arrange: セッションを作成
        beekeeper.current_session = beekeeper.session_manager.create_session()
        beekeeper.current_session.set_active()

        # Act
        await beekeeper.handle_emergency_stop({"reason": "Suspend test"})

        # Assert
        assert beekeeper.current_session.state == SessionState.SUSPENDED

    @pytest.mark.asyncio
    async def test_emergency_stop_all_closes_queens(self, beekeeper):
        """scope=allの緊急停止で全Queen Beeが閉じられる"""
        # Arrange: Queen Beeを作成
        from hiveforge.queen_bee.server import QueenBeeMCPServer

        queen = QueenBeeMCPServer(colony_id="colony-1", ar=beekeeper.ar)
        beekeeper._queens["colony-1"] = queen

        # Act
        await beekeeper.handle_emergency_stop({"reason": "All stop"})

        # Assert
        assert len(beekeeper._queens) == 0

    @pytest.mark.asyncio
    async def test_emergency_stop_colony_closes_target_only(self, beekeeper):
        """scope=colonyの緊急停止で対象Colonyのみ閉じられる"""
        # Arrange: 2つのQueen Beeを作成
        from hiveforge.queen_bee.server import QueenBeeMCPServer

        beekeeper._queens["colony-1"] = QueenBeeMCPServer(colony_id="colony-1", ar=beekeeper.ar)
        beekeeper._queens["colony-2"] = QueenBeeMCPServer(colony_id="colony-2", ar=beekeeper.ar)

        # Act
        await beekeeper.handle_emergency_stop(
            {
                "reason": "Target stop",
                "scope": "colony",
                "target_id": "colony-1",
            }
        )

        # Assert: colony-1のみ閉じられる
        assert "colony-1" not in beekeeper._queens
        assert "colony-2" in beekeeper._queens


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


class TestBeekeeperAgentRunnerPromptContext:
    """BeekeeperのAgentRunnerがvault_pathを渡すテスト"""

    @pytest.mark.asyncio
    async def test_agent_runner_receives_vault_path(self, beekeeper):
        """BeekeeperのAgentRunnerがvault_pathを受け取る

        AgentRunnerがYAMLプロンプトを読み込めるよう、
        ARのvault_pathを渡す。
        """
        # Arrange: LLMクライアントをモックで事前設定
        from unittest.mock import AsyncMock, MagicMock

        from hiveforge.llm.client import LLMClient

        mock_client = MagicMock(spec=LLMClient)
        mock_client.chat = AsyncMock()
        beekeeper._llm_client = mock_client

        # Act
        runner = await beekeeper._get_agent_runner()

        # Assert
        assert runner.vault_path == str(beekeeper.ar.vault_path)
        assert runner.agent_type == "beekeeper"

    @pytest.mark.asyncio
    async def test_agent_runner_receives_agent_info(self, beekeeper):
        """BeekeeperのAgentRunnerにAgentInfoが設定される

        ActivityBusにイベントを発行するために、
        AgentRunnerにagent_infoを渡す。
        """
        # Arrange
        from unittest.mock import AsyncMock, MagicMock

        from hiveforge.core.activity_bus import AgentRole
        from hiveforge.llm.client import LLMClient

        mock_client = MagicMock(spec=LLMClient)
        mock_client.chat = AsyncMock()
        beekeeper._llm_client = mock_client

        # Act
        runner = await beekeeper._get_agent_runner()

        # Assert
        assert runner.agent_info is not None
        assert runner.agent_info.role == AgentRole.BEEKEEPER
