"""Queen Bee MCPサーバーのテスト"""

import pytest

from colonyforge.core import AkashicRecord
from colonyforge.queen_bee.server import QueenBeeMCPServer


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
        """タスク分解（LLMモック経由で単一タスクを返す）"""
        from unittest.mock import AsyncMock

        # Arrange: _plan_tasksをモック
        queen_bee._plan_tasks = AsyncMock(
            side_effect=lambda goal, context=None: [
                {"task_id": "task-001", "goal": goal, "depends_on": []}
            ]
        )

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

    @pytest.mark.asyncio
    async def test_close_with_llm_client(self, queen_bee):
        """closeでLLMクライアントも閉じられる（L555-556）"""
        from unittest.mock import AsyncMock, MagicMock

        from colonyforge.llm.client import LLMClient

        # Arrange: LLMクライアントをモックで設定
        mock_client = MagicMock(spec=LLMClient)
        mock_client.close = AsyncMock()
        queen_bee._llm_client = mock_client

        # Act
        await queen_bee.close()

        # Assert: closeが呼ばれ、Noneになる
        mock_client.close.assert_awaited_once()
        assert queen_bee._llm_client is None


class TestExecuteGoalCoverage:
    """execute_goal のカバレッジ補完テスト"""

    @pytest.mark.asyncio
    async def test_execute_goal_exception_records_run_failed(self, queen_bee):
        """execute_goal中に例外→RunFailedイベントが記録される（L283-299）"""
        from unittest.mock import AsyncMock

        # Arrange
        queen_bee.add_worker("worker-1")
        queen_bee._plan_tasks = AsyncMock(side_effect=RuntimeError("LLM error"))

        # Act
        result = await queen_bee.handle_execute_goal({"goal": "Fail goal", "run_id": "run-fail"})

        # Assert
        assert result["status"] == "error"
        assert "LLM error" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_goal_empty_plan_uses_goal_as_task(self, queen_bee):
        """_plan_tasksが空→目標自体を1タスクとして実行（L228）"""
        from unittest.mock import AsyncMock

        # Arrange
        queen_bee.add_worker("worker-1")
        queen_bee._plan_tasks = AsyncMock(return_value=[])

        # Act
        result = await queen_bee.handle_execute_goal(
            {"goal": "Simple goal", "run_id": "run-simple"}
        )

        # Assert: 1タスクとして実行される
        assert result["tasks_total"] == 1

    @pytest.mark.asyncio
    async def test_execute_task_no_idle_workers(self, queen_bee):
        """_execute_taskでidle workerなし→error（L413）"""
        # Arrange: Workerを追加しない

        # Act
        result = await queen_bee._execute_task(
            task_id="task-1", run_id="run-1", goal="Test", context={}
        )

        # Assert
        assert result["status"] == "error"
        assert "No available workers" in result["error"]

    @pytest.mark.asyncio
    async def test_assign_task_with_worker_success(self, queen_bee):
        """assign_task成功パス（L336-340）"""
        from unittest.mock import AsyncMock

        # Arrange
        queen_bee.add_worker("worker-1")
        queen_bee._execute_task = AsyncMock(
            return_value={"status": "completed", "task_id": "task-1"}
        )

        # Act
        result = await queen_bee.handle_assign_task(
            {"task_id": "task-1", "run_id": "run-1", "goal": "Do it"}
        )

        # Assert
        assert result["status"] == "completed"


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

        from colonyforge.llm.client import LLMClient

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

        from colonyforge.core.activity_bus import AgentRole
        from colonyforge.llm.client import LLMClient

        mock_client = MagicMock(spec=LLMClient)
        mock_client.chat = AsyncMock()
        queen_bee._llm_client = mock_client

        # Act
        runner = await queen_bee._get_agent_runner()

        # Assert
        assert runner.agent_info is not None
        assert runner.agent_info.role == AgentRole.QUEEN_BEE
        assert runner.agent_info.colony_id == queen_bee.colony_id


# =========================================================================
# _plan_tasks が depends_on を保持するテスト
# =========================================================================


class TestPlanTasksDependsOn:
    """_plan_tasks() が depends_on を保持することを検証する"""

    @pytest.mark.asyncio
    async def test_plan_tasks_preserves_depends_on(self, queen_bee):
        """_plan_tasks()が各タスクのdepends_onを保持する

        LLMがdepends_on付きのタスク分解を返した場合、
        _plan_tasks()の戻り値にdepends_onが含まれることを確認。
        """
        from unittest.mock import AsyncMock, MagicMock

        from colonyforge.llm.client import LLMClient

        # Arrange: LLMが依存関係付きのタスクを返すようモック
        mock_client = MagicMock(spec=LLMClient)
        import json

        response_content = json.dumps(
            {
                "tasks": [
                    {"id": "task-1", "goal": "DB設計"},
                    {"id": "task-2", "goal": "API実装", "depends_on": ["task-1"]},
                    {"id": "task-3", "goal": "テスト", "depends_on": ["task-1", "task-2"]},
                ],
                "reasoning": "依存関係テスト",
            }
        )
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_client.chat = AsyncMock(return_value=mock_response)
        queen_bee._llm_client = mock_client

        # Act
        tasks = await queen_bee._plan_tasks("ECサイト構築", {})

        # Assert: depends_on が保持されている
        assert len(tasks) == 3
        assert tasks[0]["depends_on"] == []
        assert tasks[1]["depends_on"] == ["task-1"]
        assert tasks[2]["depends_on"] == ["task-1", "task-2"]

    @pytest.mark.asyncio
    async def test_plan_tasks_llm_failure_raises(self, queen_bee):
        """LLM失敗時に例外がそのまま伝搬される

        Fail-Fast原則に従い、フォールバックせず例外を伝搬する。
        """
        from unittest.mock import AsyncMock, MagicMock

        from colonyforge.llm.client import LLMClient

        # Arrange: LLM呼び出しが失敗
        mock_client = MagicMock(spec=LLMClient)
        mock_client.chat = AsyncMock(side_effect=RuntimeError("API error"))
        queen_bee._llm_client = mock_client

        # Act & Assert: RuntimeErrorがそのまま伝搬
        with pytest.raises(RuntimeError, match="API error"):
            await queen_bee._plan_tasks("テスト目標", {})


# =========================================================================
# _execute_direct が ColonyOrchestrator を使うテスト
# =========================================================================


class TestExecuteDirectOrchestrator:
    """_execute_direct がオーケストレータで並列実行することを検証する"""

    @pytest.mark.asyncio
    async def test_execute_direct_uses_orchestrator_for_parallel(self, queen_bee):
        """Directパスが依存関係なしタスクを並列実行する

        2つの独立タスクがオーケストレータ経由で実行され、
        ColonyResult形式の結果が返ることを確認する。
        """
        from unittest.mock import AsyncMock

        # Arrange: 2つの独立タスクを返す
        queen_bee.add_worker("worker-1")
        queen_bee.add_worker("worker-2")

        queen_bee._plan_tasks = AsyncMock(
            return_value=[
                {"task_id": "t1", "goal": "ファイルA作成", "depends_on": []},
                {"task_id": "t2", "goal": "ファイルB作成", "depends_on": []},
            ]
        )
        queen_bee._execute_task = AsyncMock(return_value={"status": "completed", "result": "ok"})

        # Act
        result = await queen_bee._execute_direct("run-1", "2ファイル作成", {})

        # Assert: 2タスクとも完了
        assert result["status"] == "completed"
        assert result["tasks_total"] == 2
        assert result["tasks_completed"] == 2

    @pytest.mark.asyncio
    async def test_execute_direct_respects_dependencies(self, queen_bee):
        """Directパスが依存関係を尊重して実行する

        task-2がtask-1に依存する場合、task-1の完了後にtask-2が実行される。
        task-1が失敗するとtask-2はスキップされる。
        """
        from unittest.mock import AsyncMock

        # Arrange: task-1が失敗する設定
        queen_bee.add_worker("worker-1")

        queen_bee._plan_tasks = AsyncMock(
            return_value=[
                {"task_id": "t1", "goal": "基盤構築", "depends_on": []},
                {"task_id": "t2", "goal": "機能実装", "depends_on": ["t1"]},
            ]
        )
        queen_bee._execute_task = AsyncMock(return_value={"status": "failed", "reason": "エラー"})

        # Act
        result = await queen_bee._execute_direct("run-1", "段階的構築", {})

        # Assert: 1タスクが失敗し1タスクがスキップ、全体はpartial
        assert result["status"] == "partial"
        assert result["tasks_total"] == 2
        # スキップされたタスクも記録される
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_execute_direct_propagates_context(self, queen_bee):
        """Directパスで先行タスクの結果が後続に伝搬する

        task-1の出力が、task-2のコンテキストに含まれることを確認。
        """
        from unittest.mock import AsyncMock

        # Arrange
        queen_bee.add_worker("worker-1")

        queen_bee._plan_tasks = AsyncMock(
            return_value=[
                {"task_id": "t1", "goal": "設計書作成", "depends_on": []},
                {"task_id": "t2", "goal": "実装", "depends_on": ["t1"]},
            ]
        )

        call_contexts = []

        async def capture_execute(task_id, run_id, goal, context, worker=None):
            call_contexts.append({"task_id": task_id, "context": context})
            return {"status": "completed", "result": f"{task_id}完了"}

        queen_bee._execute_task = capture_execute

        # Act
        result = await queen_bee._execute_direct("run-1", "設計→実装", {})

        # Assert: 2番目のタスクにはpredecessor_resultsが含まれる
        assert result["status"] == "completed"
        assert len(call_contexts) == 2
        # t2のcontextに先行タスクの結果が含まれる
        t2_ctx = call_contexts[1]["context"]
        assert t2_ctx is not None
        assert "predecessor_results" in t2_ctx
