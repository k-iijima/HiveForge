"""Queen Bee MCPサーバーのテスト"""

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.queen_bee.server import QueenBeeMCPServer


@pytest.fixture
def ar(tmp_path):
    """テスト用Akashic Record"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def queen_bee(ar):
    """テスト用Queen Bee"""
    return QueenBeeMCPServer(colony_id="colony-1", ar=ar)


class TestQueenBeeMCPServer:
    """Queen Bee MCPサーバーの基本テスト"""

    def test_initialization(self, queen_bee):
        """Queen Beeが正しく初期化される"""
        # Assert
        assert queen_bee.colony_id == "colony-1"
        assert queen_bee.ar is not None
        assert len(queen_bee._workers) == 0

    def test_get_tool_definitions(self, queen_bee):
        """ツール定義が正しく取得できる"""
        # Act
        tools = queen_bee.get_tool_definitions()

        # Assert
        tool_names = [t["name"] for t in tools]
        assert "execute_goal" in tool_names
        assert "plan_tasks" in tool_names
        assert "assign_task" in tool_names
        assert "get_colony_status" in tool_names
        assert "add_worker" in tool_names
        assert "remove_worker" in tool_names


class TestWorkerManagement:
    """Worker管理のテスト"""

    def test_add_worker(self, queen_bee):
        """Workerを追加"""
        # Act
        worker = queen_bee.add_worker("worker-1")

        # Assert
        assert worker.worker_id == "worker-1"
        assert "worker-1" in queen_bee._workers

    def test_add_worker_idempotent(self, queen_bee):
        """同じWorkerを2回追加しても1つ"""
        # Act
        worker1 = queen_bee.add_worker("worker-1")
        worker2 = queen_bee.add_worker("worker-1")

        # Assert
        assert worker1 is worker2
        assert len(queen_bee._workers) == 1

    def test_remove_worker(self, queen_bee):
        """Workerを削除"""
        # Arrange
        queen_bee.add_worker("worker-1")

        # Act
        result = queen_bee.remove_worker("worker-1")

        # Assert
        assert result is True
        assert "worker-1" not in queen_bee._workers

    def test_remove_nonexistent_worker(self, queen_bee):
        """存在しないWorkerの削除"""
        # Act
        result = queen_bee.remove_worker("nonexistent")

        # Assert
        assert result is False

    def test_get_idle_workers(self, queen_bee):
        """IDLEなWorkerを取得"""
        # Arrange
        queen_bee.add_worker("worker-1")
        queen_bee.add_worker("worker-2")

        # Act
        idle = queen_bee.get_idle_workers()

        # Assert
        assert len(idle) == 2

    def test_get_worker(self, queen_bee):
        """Workerを取得"""
        # Arrange
        queen_bee.add_worker("worker-1")

        # Act
        worker = queen_bee.get_worker("worker-1")

        # Assert
        assert worker is not None
        assert worker.worker_id == "worker-1"

    def test_get_nonexistent_worker(self, queen_bee):
        """存在しないWorkerの取得"""
        # Act
        worker = queen_bee.get_worker("nonexistent")

        # Assert
        assert worker is None


class TestHandleAddRemoveWorker:
    """add_worker/remove_workerハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_handle_add_worker(self, queen_bee):
        """Worker追加ハンドラ"""
        # Act
        result = await queen_bee.handle_add_worker({"worker_id": "worker-1"})

        # Assert
        assert result["status"] == "added"
        assert result["worker_id"] == "worker-1"
        assert result["colony_id"] == "colony-1"

    @pytest.mark.asyncio
    async def test_handle_remove_worker(self, queen_bee):
        """Worker削除ハンドラ"""
        # Arrange
        await queen_bee.handle_add_worker({"worker_id": "worker-1"})

        # Act
        result = await queen_bee.handle_remove_worker({"worker_id": "worker-1"})

        # Assert
        assert result["status"] == "removed"

    @pytest.mark.asyncio
    async def test_handle_remove_nonexistent(self, queen_bee):
        """存在しないWorker削除"""
        # Act
        result = await queen_bee.handle_remove_worker({"worker_id": "nonexistent"})

        # Assert
        assert "error" in result


class TestHandleGetColonyStatus:
    """get_colony_statusハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_get_colony_status_empty(self, queen_bee):
        """Workerなしの状態取得"""
        # Act
        result = await queen_bee.handle_get_colony_status({})

        # Assert
        assert result["status"] == "success"
        assert result["colony_id"] == "colony-1"
        assert result["worker_count"] == 0
        assert result["idle_count"] == 0

    @pytest.mark.asyncio
    async def test_get_colony_status_with_workers(self, queen_bee):
        """Workerありの状態取得"""
        # Arrange
        queen_bee.add_worker("worker-1")
        queen_bee.add_worker("worker-2")

        # Act
        result = await queen_bee.handle_get_colony_status({})

        # Assert
        assert result["worker_count"] == 2
        assert result["idle_count"] == 2
        assert len(result["workers"]) == 2


class TestHandlePlanTasks:
    """plan_tasksハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_plan_tasks_returns_single_task(self, queen_bee):
        """タスク分解（現時点では単一タスクを返す）"""
        # Act
        result = await queen_bee.handle_plan_tasks(
            {
                "goal": "Create a hello world program",
            }
        )

        # Assert
        assert result["status"] == "success"
        assert result["goal"] == "Create a hello world program"
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["goal"] == "Create a hello world program"


class TestHandleAssignTask:
    """assign_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_assign_task_no_workers(self, queen_bee):
        """Workerなしでタスク割り当て"""
        # Act
        result = await queen_bee.handle_assign_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Do something",
            }
        )

        # Assert
        assert "error" in result
        assert "No available workers" in result["error"]

    @pytest.mark.asyncio
    async def test_assign_task_worker_not_found(self, queen_bee):
        """指定Workerが存在しない"""
        # Arrange
        queen_bee.add_worker("worker-1")

        # Act
        result = await queen_bee.handle_assign_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Do something",
                "worker_id": "nonexistent",
            }
        )

        # Assert
        assert "error" in result
        assert "not found" in result["error"]


class TestDispatchTool:
    """dispatch_toolのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_get_colony_status(self, queen_bee):
        """get_colony_statusがディスパッチされる"""
        result = await queen_bee.dispatch_tool("get_colony_status", {})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self, queen_bee):
        """未知のツールはエラー"""
        result = await queen_bee.dispatch_tool("unknown_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]


class TestClose:
    """closeのテスト"""

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, queen_bee):
        """closeでリソースが解放される"""
        # Arrange
        queen_bee.add_worker("worker-1")

        # Act
        await queen_bee.close()

        # Assert
        assert queen_bee._llm_client is None
        assert queen_bee._agent_runner is None


class TestQueenBeeAgentRunnerPromptContext:
    """Queen BeeのAgentRunnerがvault_pathとcolony_idを渡すテスト"""

    @pytest.mark.asyncio
    async def test_agent_runner_receives_vault_path_and_colony_id(self, queen_bee):
        """Queen BeeのAgentRunnerがvault_pathとcolony_idを受け取る

        AgentRunnerがYAMLプロンプトを読み込めるよう、
        ARのvault_pathとColony IDを渡す。
        """
        # Arrange: LLMクライアントをモックで事前設定
        from unittest.mock import AsyncMock, MagicMock

        from hiveforge.llm.client import LLMClient

        mock_client = MagicMock(spec=LLMClient)
        mock_client.chat = AsyncMock()
        queen_bee._llm_client = mock_client

        # Act
        runner = await queen_bee._get_agent_runner()

        # Assert
        assert runner.vault_path == str(queen_bee.ar.vault_path)
        assert runner.colony_id == queen_bee.colony_id
        assert runner.agent_type == "queen_bee"

    @pytest.mark.asyncio
    async def test_agent_runner_receives_agent_info(self, queen_bee):
        """Queen BeeのAgentRunnerにAgentInfoが設定される"""
        # Arrange
        from unittest.mock import AsyncMock, MagicMock

        from hiveforge.core.activity_bus import AgentRole
        from hiveforge.llm.client import LLMClient

        mock_client = MagicMock(spec=LLMClient)
        mock_client.chat = AsyncMock()
        queen_bee._llm_client = mock_client

        # Act
        runner = await queen_bee._get_agent_runner()

        # Assert
        assert runner.agent_info is not None
        assert runner.agent_info.role == AgentRole.QUEEN_BEE
        assert runner.agent_info.colony_id == queen_bee.colony_id
