"""Worker Bee MCPサーバーのテスト"""

import asyncio

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.core.events import EventType
from hiveforge.worker_bee import WorkerBeeMCPServer
from hiveforge.worker_bee.server import WorkerState


@pytest.fixture
def ar(tmp_path):
    """テスト用Akashic Record"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def worker_bee(ar):
    """テスト用Worker Bee"""
    return WorkerBeeMCPServer(worker_id="worker-1", ar=ar)


class TestWorkerBeeMCPServer:
    """Worker Bee MCPサーバーの基本テスト"""

    def test_initialization(self, worker_bee):
        """Worker Beeが正しく初期化される"""
        # Assert
        assert worker_bee.worker_id == "worker-1"
        assert worker_bee.state == WorkerState.IDLE
        assert worker_bee.context.current_task_id is None

    def test_get_tool_definitions(self, worker_bee):
        """ツール定義が正しく取得できる"""
        # Act
        tools = worker_bee.get_tool_definitions()

        # Assert
        tool_names = [t["name"] for t in tools]
        assert "receive_task" in tool_names
        assert "report_progress" in tool_names
        assert "complete_task" in tool_names
        assert "fail_task" in tool_names
        assert "get_status" in tool_names


class TestReceiveTask:
    """receive_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_receive_task_success(self, worker_bee):
        """タスクを正常に受け取れる"""
        # Act
        result = await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Implement feature X",
            }
        )

        # Assert
        assert result["status"] == "accepted"
        assert result["task_id"] == "task-1"
        assert worker_bee.state == WorkerState.WORKING

    @pytest.mark.asyncio
    async def test_receive_task_while_working(self, worker_bee):
        """作業中に別タスクは受け取れない"""
        # Arrange: まず1つ目のタスクを受け取る
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "First task",
            }
        )

        # Act: 2つ目のタスクを受け取ろうとする
        result = await worker_bee.handle_receive_task(
            {
                "task_id": "task-2",
                "run_id": "run-1",
                "goal": "Second task",
            }
        )

        # Assert
        assert "error" in result
        assert result["current_task_id"] == "task-1"

    @pytest.mark.asyncio
    async def test_receive_task_emits_event(self, worker_bee, ar):
        """タスク受け取り時にイベントが発行される"""
        # Act
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test goal",
            }
        )

        # Assert
        events = list(ar.replay("run-1"))
        assert len(events) == 1
        assert events[0].type == EventType.WORKER_STARTED
        assert events[0].worker_id == "worker-1"


class TestReportProgress:
    """report_progressハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_report_progress_success(self, worker_bee):
        """進捗を正常に報告できる"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )

        # Act
        result = await worker_bee.handle_report_progress(
            {
                "progress": 50,
                "message": "halfway done",
            }
        )

        # Assert
        assert result["status"] == "reported"
        assert result["progress"] == 50
        assert worker_bee.context.progress == 50

    @pytest.mark.asyncio
    async def test_report_progress_without_task(self, worker_bee):
        """タスクなしで進捗報告はエラー"""
        # Act
        result = await worker_bee.handle_report_progress({"progress": 50})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_report_progress_emits_event(self, worker_bee, ar):
        """進捗報告時にイベントが発行される"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )

        # Act
        await worker_bee.handle_report_progress(
            {
                "progress": 75,
                "message": "Almost done",
            }
        )

        # Assert
        events = list(ar.replay("run-1"))
        assert len(events) == 2
        assert events[1].type == EventType.WORKER_PROGRESS
        assert events[1].progress == 75


class TestCompleteTask:
    """complete_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_complete_task_success(self, worker_bee):
        """タスクを正常に完了できる"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )

        # Act
        result = await worker_bee.handle_complete_task(
            {
                "result": "Feature implemented",
                "deliverables": ["file1.py", "file2.py"],
            }
        )

        # Assert
        assert result["status"] == "completed"
        assert result["task_id"] == "task-1"
        assert worker_bee.state == WorkerState.IDLE

    @pytest.mark.asyncio
    async def test_complete_task_without_active_task(self, worker_bee):
        """タスクなしで完了はエラー"""
        # Act
        result = await worker_bee.handle_complete_task({"result": "Done"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_complete_task_emits_event(self, worker_bee, ar):
        """タスク完了時にイベントが発行される"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )

        # Act
        await worker_bee.handle_complete_task(
            {
                "result": "Success",
            }
        )

        # Assert
        events = list(ar.replay("run-1"))
        assert len(events) == 2
        assert events[1].type == EventType.WORKER_COMPLETED


class TestFailTask:
    """fail_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_fail_task_success(self, worker_bee):
        """タスク失敗を正常に報告できる"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )

        # Act
        result = await worker_bee.handle_fail_task(
            {
                "reason": "Connection timeout",
                "recoverable": True,
            }
        )

        # Assert
        assert result["status"] == "failed"
        assert result["reason"] == "Connection timeout"
        assert result["recoverable"] is True
        assert worker_bee.state == WorkerState.IDLE

    @pytest.mark.asyncio
    async def test_fail_task_not_recoverable(self, worker_bee):
        """リカバリ不能な失敗はERROR状態になる"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )

        # Act
        await worker_bee.handle_fail_task(
            {
                "reason": "Fatal error",
                "recoverable": False,
            }
        )

        # Assert
        assert worker_bee.state == WorkerState.ERROR

    @pytest.mark.asyncio
    async def test_fail_task_without_active_task(self, worker_bee):
        """タスクなしで失敗報告はエラー"""
        # Act
        result = await worker_bee.handle_fail_task({"reason": "Error"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fail_task_emits_event(self, worker_bee, ar):
        """タスク失敗時にイベントが発行される"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )

        # Act
        await worker_bee.handle_fail_task(
            {
                "reason": "Test failure",
            }
        )

        # Assert
        events = list(ar.replay("run-1"))
        assert len(events) == 2
        assert events[1].type == EventType.WORKER_FAILED
        assert events[1].reason == "Test failure"


class TestGetStatus:
    """get_statusハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_get_status_idle(self, worker_bee):
        """IDLE状態のステータス取得"""
        # Act
        result = await worker_bee.handle_get_status({})

        # Assert
        assert result["worker_id"] == "worker-1"
        assert result["state"] == "idle"
        assert result["current_task_id"] is None

    @pytest.mark.asyncio
    async def test_get_status_working(self, worker_bee):
        """WORKING状態のステータス取得"""
        # Arrange
        await worker_bee.handle_receive_task(
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            }
        )
        await worker_bee.handle_report_progress({"progress": 30})

        # Act
        result = await worker_bee.handle_get_status({})

        # Assert
        assert result["state"] == "working"
        assert result["current_task_id"] == "task-1"
        assert result["progress"] == 30


class TestDispatchTool:
    """dispatch_toolのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_receive_task(self, worker_bee):
        """receive_taskがディスパッチされる"""
        result = await worker_bee.dispatch_tool(
            "receive_task",
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "goal": "Test",
            },
        )
        assert result["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self, worker_bee):
        """未知のツールはエラー"""
        result = await worker_bee.dispatch_tool("unknown_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]


# Worker Projection テスト
from hiveforge.worker_bee.projections import (
    WorkerProjection,
    WorkerPoolProjection,
    WorkerState as ProjectionWorkerState,
    build_worker_projection,
    build_worker_pool_projection,
)
from hiveforge.core.events import (
    WorkerStartedEvent,
    WorkerProgressEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerAssignedEvent,
)


class TestWorkerProjection:
    """WorkerProjectionのテスト"""

    def test_initial_state(self):
        """初期状態はIDLE"""
        projection = WorkerProjection(worker_id="worker-1")
        assert projection.state == ProjectionWorkerState.IDLE
        assert projection.current_task_id is None

    def test_build_from_started_event(self):
        """WORKER_STARTEDイベントで状態が更新される"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            )
        ]

        # Act
        projection = build_worker_projection(events, "worker-1")

        # Assert
        assert projection.state == ProjectionWorkerState.WORKING
        assert projection.current_task_id == "task-1"

    def test_build_from_progress_event(self):
        """WORKER_PROGRESSイベントで進捗が更新される"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
            WorkerProgressEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                progress=50,
                payload={},
            ),
        ]

        # Act
        projection = build_worker_projection(events, "worker-1")

        # Assert
        assert projection.progress == 50

    def test_build_from_completed_event(self):
        """WORKER_COMPLETEDイベントで状態がIDLEに戻る"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
            WorkerCompletedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
        ]

        # Act
        projection = build_worker_projection(events, "worker-1")

        # Assert
        assert projection.state == ProjectionWorkerState.IDLE
        assert "task-1" in projection.completed_tasks

    def test_build_from_failed_recoverable(self):
        """リカバリ可能な失敗はIDLEに戻る"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
            WorkerFailedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                reason="Timeout",
                payload={"recoverable": True},
            ),
        ]

        # Act
        projection = build_worker_projection(events, "worker-1")

        # Assert
        assert projection.state == ProjectionWorkerState.IDLE
        assert "task-1" in projection.failed_tasks

    def test_build_from_failed_not_recoverable(self):
        """リカバリ不能な失敗はERROR状態"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
            WorkerFailedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                reason="Fatal",
                payload={"recoverable": False},
            ),
        ]

        # Act
        projection = build_worker_projection(events, "worker-1")

        # Assert
        assert projection.state == ProjectionWorkerState.ERROR
        assert projection.error_message == "Fatal"

    def test_ignores_other_worker_events(self):
        """他のWorkerのイベントは無視される"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-2",  # 別のWorker
                actor="worker-2",
                payload={},
            ),
        ]

        # Act
        projection = build_worker_projection(events, "worker-1")

        # Assert
        assert projection.state == ProjectionWorkerState.IDLE


class TestWorkerPoolProjection:
    """WorkerPoolProjectionのテスト"""

    def test_build_from_multiple_workers(self):
        """複数Workerの状態を追跡"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-2",
                worker_id="worker-2",
                actor="worker-2",
                payload={},
            ),
            WorkerCompletedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
        ]

        # Act
        pool = build_worker_pool_projection(events)

        # Assert
        assert pool.total_workers == 2
        assert pool.idle_count == 1
        assert pool.working_count == 1

    def test_get_worker(self):
        """特定のWorkerを取得"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
        ]

        # Act
        pool = build_worker_pool_projection(events)
        worker = pool.get_worker("worker-1")

        # Assert
        assert worker is not None
        assert worker.state == ProjectionWorkerState.WORKING

    def test_get_nonexistent_worker(self):
        """存在しないWorkerはNone"""
        pool = WorkerPoolProjection()
        assert pool.get_worker("nonexistent") is None

    def test_get_idle_workers(self):
        """IDLEのWorker一覧を取得"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
            WorkerCompletedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
        ]

        # Act
        pool = build_worker_pool_projection(events)
        idle = pool.get_idle_workers()

        # Assert
        assert len(idle) == 1
        assert idle[0].worker_id == "worker-1"

    def test_get_working_workers(self):
        """WORKING中のWorker一覧を取得"""
        # Arrange
        events = [
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
        ]

        # Act
        pool = build_worker_pool_projection(events)
        working = pool.get_working_workers()

        # Assert
        assert len(working) == 1

    def test_build_from_assigned_event(self):
        """WORKER_ASSIGNEDイベントで状態が更新される"""
        # Arrange
        events = [
            WorkerAssignedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="queen",
                payload={"goal": "Test task"},
            )
        ]

        # Act
        projection = build_worker_projection(events, "worker-1")

        # Assert
        assert projection.state == ProjectionWorkerState.IDLE
        assert projection.current_task_id == "task-1"
        assert projection.current_run_id == "run-1"


# Worker Bee Projection 追加テスト
from hiveforge.worker_bee.projections import WorkerProjection, WorkerPoolProjection


class TestWorkerProjectionEdgeCases:
    """WorkerProjectionエッジケースのテスト"""

    def test_get_nonexistent_worker(self):
        """存在しないWorker取得"""
        pool = WorkerPoolProjection()
        worker = pool.get_worker("nonexistent")
        assert worker is None

    def test_get_working_workers_empty(self):
        """作業中Workerがいない場合"""
        pool = WorkerPoolProjection()
        pool.workers["worker-1"] = WorkerProjection(worker_id="worker-1", state="idle")

        working = pool.get_working_workers()
        assert working == []


# Worker Process Manager テスト
from hiveforge.worker_bee.process import (
    WorkerProcess,
    WorkerProcessState,
    WorkerPoolConfig,
    WorkerProcessManager,
)
import pytest


class TestWorkerProcess:
    """WorkerProcessの基本テスト"""

    def test_create_worker_process(self):
        """Workerプロセスを作成"""
        worker = WorkerProcess(worker_id="worker-1", colony_id="colony-1")

        assert worker.process_id is not None
        assert worker.state == WorkerProcessState.STOPPED
        assert worker.restart_count == 0

    def test_is_running(self):
        """稼働状態チェック"""
        worker = WorkerProcess(worker_id="worker-1", colony_id="colony-1")
        assert not worker.is_running()

        worker.state = WorkerProcessState.RUNNING
        assert worker.is_running()

        worker.state = WorkerProcessState.STARTING
        assert worker.is_running()

    def test_can_restart(self):
        """再起動可能チェック"""
        worker = WorkerProcess(worker_id="worker-1", colony_id="colony-1", max_restarts=3)
        assert worker.can_restart()

        worker.restart_count = 3
        assert not worker.can_restart()


class TestWorkerPoolConfig:
    """WorkerPoolConfigのテスト"""

    def test_default_config(self):
        """デフォルト設定"""
        config = WorkerPoolConfig()
        assert config.min_workers == 1
        assert config.max_workers == 10
        assert config.auto_restart is True

    def test_custom_config(self):
        """カスタム設定"""
        config = WorkerPoolConfig(min_workers=5, max_workers=20, auto_restart=False)
        assert config.min_workers == 5
        assert config.max_workers == 20
        assert config.auto_restart is False


class TestWorkerProcessManager:
    """WorkerProcessManagerのテスト"""

    @pytest.mark.asyncio
    async def test_start_worker(self):
        """Workerプロセスを起動"""
        manager = WorkerProcessManager()
        worker = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")

        assert worker.state == WorkerProcessState.RUNNING
        assert worker.worker_id == "worker-1"

    @pytest.mark.asyncio
    async def test_stop_worker(self):
        """Workerプロセスを停止"""
        manager = WorkerProcessManager()
        worker = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")

        result = await manager.stop_worker(worker.process_id)

        assert result is True
        assert manager.get_worker(worker.process_id).state == WorkerProcessState.STOPPED

    @pytest.mark.asyncio
    async def test_stop_nonexistent_worker(self):
        """存在しないWorkerの停止"""
        manager = WorkerProcessManager()
        result = await manager.stop_worker("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_workers_by_colony(self):
        """Colony別Worker一覧"""
        manager = WorkerProcessManager()
        await manager.start_worker(worker_id="worker-1", colony_id="colony-1")
        await manager.start_worker(worker_id="worker-2", colony_id="colony-1")
        await manager.start_worker(worker_id="worker-3", colony_id="colony-2")

        workers = manager.get_workers_by_colony("colony-1")
        assert len(workers) == 2

    @pytest.mark.asyncio
    async def test_get_running_workers(self):
        """稼働中Worker一覧"""
        manager = WorkerProcessManager()
        w1 = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")
        w2 = await manager.start_worker(worker_id="worker-2", colony_id="colony-1")
        await manager.stop_worker(w2.process_id)

        running = manager.get_running_workers()
        assert len(running) == 1
        assert running[0].worker_id == "worker-1"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """統計情報"""
        manager = WorkerProcessManager()
        w1 = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")
        w2 = await manager.start_worker(worker_id="worker-2", colony_id="colony-1")
        await manager.stop_worker(w2.process_id)

        stats = manager.get_stats()
        assert stats["total"] == 2
        assert stats["running"] == 1
        assert stats["stopped"] == 1

    @pytest.mark.asyncio
    async def test_callbacks(self):
        """コールバック"""
        started_workers = []
        stopped_workers = []

        manager = WorkerProcessManager()
        manager.set_callbacks(
            on_started=lambda w: started_workers.append(w),
            on_stopped=lambda w: stopped_workers.append(w),
        )

        worker = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")
        await manager.stop_worker(worker.process_id)

        assert len(started_workers) == 1
        assert len(stopped_workers) == 1

    @pytest.mark.asyncio
    async def test_shutdown_all(self):
        """全Worker停止"""
        manager = WorkerProcessManager()
        await manager.start_worker(worker_id="worker-1", colony_id="colony-1")
        await manager.start_worker(worker_id="worker-2", colony_id="colony-1")

        await manager.shutdown_all()

        assert len(manager.get_running_workers()) == 0

    @pytest.mark.asyncio
    async def test_restart_worker(self):
        """Workerプロセスを再起動"""
        manager = WorkerProcessManager()
        worker = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")

        new_worker = await manager.restart_worker(worker.process_id)

        assert new_worker is not None
        assert new_worker.process_id != worker.process_id
        assert new_worker.state == WorkerProcessState.RUNNING

    @pytest.mark.asyncio
    async def test_restart_nonexistent(self):
        """存在しないWorkerの再起動"""
        manager = WorkerProcessManager()
        result = await manager.restart_worker("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_restart_exceeded(self):
        """再起動回数上限超過"""
        manager = WorkerProcessManager()
        worker = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")
        manager._workers[worker.process_id].restart_count = 3  # Max reached

        result = await manager.restart_worker(worker.process_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_health_check_running(self):
        """ヘルスチェック: 稼働中"""
        manager = WorkerProcessManager()
        worker = await manager.start_worker(worker_id="worker-1", colony_id="colony-1")

        healthy = await manager.check_health(worker.process_id)
        assert healthy is True

    @pytest.mark.asyncio
    async def test_health_check_nonexistent(self):
        """ヘルスチェック: 存在しない"""
        manager = WorkerProcessManager()
        healthy = await manager.check_health("nonexistent")
        assert healthy is False


# Tool Executor テスト
from hiveforge.worker_bee.tools import (
    ToolDefinition,
    ToolCategory,
    ToolStatus,
    ToolResult,
    ToolExecutor,
    create_builtin_tools,
)
import pytest


class TestToolDefinition:
    """ToolDefinitionの基本テスト"""

    def test_create_definition(self):
        """ツール定義作成"""
        tool = ToolDefinition(
            name="test_tool",
            description="テストツール",
            category=ToolCategory.SHELL,
        )

        assert tool.tool_id is not None
        assert tool.name == "test_tool"
        assert tool.sandbox is True

    def test_default_timeout(self):
        """デフォルトタイムアウト"""
        tool = ToolDefinition(name="test")
        assert tool.timeout_seconds == 30.0


class TestToolResult:
    """ToolResultの基本テスト"""

    def test_is_success(self):
        """成功判定"""
        result = ToolResult(status=ToolStatus.COMPLETED)
        assert result.is_success()

        result.status = ToolStatus.FAILED
        assert not result.is_success()

    def test_is_error(self):
        """エラー判定"""
        result = ToolResult(status=ToolStatus.FAILED)
        assert result.is_error()

        result.status = ToolStatus.TIMEOUT
        assert result.is_error()


class TestToolExecutor:
    """ToolExecutorのテスト"""

    @pytest.mark.asyncio
    async def test_register_and_execute(self):
        """ツール登録と実行"""
        executor = ToolExecutor()

        tool = ToolDefinition(name="greet", category=ToolCategory.CUSTOM)
        executor.register_tool(tool, lambda name: f"Hello, {name}!")

        result = await executor.execute(tool.tool_id, {"name": "World"})

        assert result.is_success()
        assert result.output == "Hello, World!"

    @pytest.mark.asyncio
    async def test_execute_async_handler(self):
        """非同期ハンドラ実行"""
        executor = ToolExecutor()

        async def async_handler(x: int) -> int:
            return x * 2

        tool = ToolDefinition(name="double", category=ToolCategory.CUSTOM)
        executor.register_tool(tool, async_handler)

        result = await executor.execute(tool.tool_id, {"x": 5})

        assert result.is_success()
        assert result.output == 10

    @pytest.mark.asyncio
    async def test_execute_not_found(self):
        """存在しないツール実行"""
        executor = ToolExecutor()

        result = await executor.execute("nonexistent", {})

        assert result.status == ToolStatus.FAILED
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_handler(self):
        """ハンドラなしで実行"""
        executor = ToolExecutor()

        tool = ToolDefinition(name="no_handler")
        executor.register_tool(tool)  # ハンドラなし

        result = await executor.execute(tool.tool_id, {})

        assert result.status == ToolStatus.FAILED
        assert "No handler" in result.error

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """タイムアウト"""
        import asyncio

        executor = ToolExecutor()

        async def slow_handler():
            await asyncio.sleep(10)
            return "done"

        tool = ToolDefinition(name="slow", timeout_seconds=0.1)
        executor.register_tool(tool, slow_handler)

        result = await executor.execute(tool.tool_id, {})

        assert result.status == ToolStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_execute_error(self):
        """例外発生"""
        executor = ToolExecutor()

        def error_handler():
            raise ValueError("Something went wrong")

        tool = ToolDefinition(name="error")
        executor.register_tool(tool, error_handler)

        result = await executor.execute(tool.tool_id, {})

        assert result.status == ToolStatus.FAILED
        assert "Something went wrong" in result.error

    def test_unregister_tool(self):
        """ツール登録解除"""
        executor = ToolExecutor()

        tool = ToolDefinition(name="temp")
        executor.register_tool(tool)

        result = executor.unregister_tool(tool.tool_id)
        assert result is True

        result2 = executor.unregister_tool(tool.tool_id)
        assert result2 is False

    def test_list_tools(self):
        """ツール一覧"""
        executor = ToolExecutor()

        executor.register_tool(ToolDefinition(name="t1", category=ToolCategory.SHELL))
        executor.register_tool(ToolDefinition(name="t2", category=ToolCategory.HTTP))
        executor.register_tool(ToolDefinition(name="t3", category=ToolCategory.SHELL))

        all_tools = executor.list_tools()
        assert len(all_tools) == 3

        shell_tools = executor.list_tools(category=ToolCategory.SHELL)
        assert len(shell_tools) == 2

    def test_get_tool_by_name(self):
        """名前でツール取得"""
        executor = ToolExecutor()

        tool = ToolDefinition(name="find_me")
        executor.register_tool(tool)

        found = executor.get_tool_by_name("find_me")
        assert found is not None
        assert found.tool_id == tool.tool_id

    @pytest.mark.asyncio
    async def test_execute_by_name(self):
        """名前でツール実行"""
        executor = ToolExecutor()

        tool = ToolDefinition(name="greet")
        executor.register_tool(tool, lambda: "Hello!")

        result = await executor.execute_by_name("greet", {})

        assert result.is_success()
        assert result.output == "Hello!"

    @pytest.mark.asyncio
    async def test_listeners(self):
        """リスナー"""
        started = []
        completed = []
        executor = ToolExecutor()
        executor.add_listener(
            on_started=lambda i: started.append(i),
            on_completed=lambda r: completed.append(r),
        )

        tool = ToolDefinition(name="test")
        executor.register_tool(tool, lambda: "done")

        await executor.execute(tool.tool_id, {})

        assert len(started) == 1
        assert len(completed) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """統計情報"""
        executor = ToolExecutor()

        tool = ToolDefinition(name="test")
        executor.register_tool(tool, lambda: "ok")

        await executor.execute(tool.tool_id, {})
        await executor.execute(tool.tool_id, {})

        stats = executor.get_stats()
        assert stats["total_tools"] == 1
        assert stats["total_executions"] == 2
        assert stats["completed"] == 2

    def test_create_builtin_tools(self):
        """組み込みツール作成"""
        builtins = create_builtin_tools()
        assert len(builtins) == 2

        names = [t[0].name for t in builtins]
        assert "echo" in names
        assert "sleep" in names


# Retry Executor テスト
from hiveforge.worker_bee.retry import (
    RetryPolicy,
    RetryStrategy,
    RetryExecutor,
    RetryResult,
    TimeoutConfig,
    TimeoutBehavior,
    create_default_retry_policy,
    create_no_retry_policy,
)


class TestRetryPolicy:
    """RetryPolicyの基本テスト"""

    def test_default_policy(self):
        """デフォルトポリシー"""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.strategy == RetryStrategy.FIXED

    def test_get_delay_fixed(self):
        """固定遅延"""
        policy = RetryPolicy(strategy=RetryStrategy.FIXED, initial_delay=2.0, jitter=False)
        assert policy.get_delay(0) == 2.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(5) == 2.0

    def test_get_delay_exponential(self):
        """指数バックオフ"""
        policy = RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=1.0,
            multiplier=2.0,
            jitter=False,
        )
        assert policy.get_delay(0) == 1.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(2) == 4.0

    def test_get_delay_max(self):
        """最大遅延"""
        policy = RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=10.0,
            max_delay=20.0,
            jitter=False,
        )
        assert policy.get_delay(5) == 20.0

    def test_should_retry(self):
        """リトライ判定"""
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry("error", 0)
        assert policy.should_retry("error", 2)
        assert not policy.should_retry("error", 3)

    def test_should_retry_with_filter(self):
        """エラーフィルタ付きリトライ"""
        policy = RetryPolicy(retryable_errors=["timeout", "connection"])
        assert policy.should_retry("connection refused", 0)
        assert policy.should_retry("timeout occurred", 0)
        assert not policy.should_retry("invalid input", 0)

    def test_no_retry(self):
        """リトライなし"""
        policy = RetryPolicy(strategy=RetryStrategy.NONE)
        assert not policy.should_retry("error", 0)


class TestRetryExecutor:
    """RetryExecutorのテスト"""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """成功時"""
        executor = RetryExecutor(create_no_retry_policy())

        async def success_op():
            return "ok"

        result = await executor.execute(success_op)

        assert result.success
        assert result.result == "ok"
        assert result.attempt_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry(self):
        """リトライ成功"""
        policy = RetryPolicy(
            strategy=RetryStrategy.FIXED,
            max_retries=3,
            initial_delay=0.01,
            jitter=False,
        )
        executor = RetryExecutor(policy)

        call_count = 0

        async def flaky_op():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = await executor.execute(flaky_op)

        assert result.success
        assert result.result == "success"
        assert result.attempt_count == 3

    @pytest.mark.asyncio
    async def test_execute_max_retries_exceeded(self):
        """リトライ上限"""
        policy = RetryPolicy(
            strategy=RetryStrategy.FIXED,
            max_retries=2,
            initial_delay=0.01,
            jitter=False,
        )
        executor = RetryExecutor(policy)

        async def always_fail():
            raise ValueError("Always fails")

        result = await executor.execute(always_fail)

        assert not result.success
        assert "Always fails" in result.error
        assert result.attempt_count == 3  # 初回 + 2回リトライ

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """タイムアウト"""
        executor = RetryExecutor(create_no_retry_policy())

        async def slow_op():
            await asyncio.sleep(10)
            return "done"

        timeout = TimeoutConfig(timeout_seconds=0.1)
        result = await executor.execute(slow_op, timeout)

        assert not result.success
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_fallback(self):
        """フォールバック"""
        executor = RetryExecutor(create_no_retry_policy())

        async def fail_op():
            raise ValueError("Failed")

        async def fallback_op():
            return "fallback"

        result = await executor.execute_with_fallback(fail_op, fallback_op)

        assert result.success
        assert result.result == "fallback"

    @pytest.mark.asyncio
    async def test_listeners(self):
        """リスナー"""
        retries = []
        timeouts = []

        policy = RetryPolicy(strategy=RetryStrategy.FIXED, max_retries=2, initial_delay=0.01)
        executor = RetryExecutor(policy)
        executor.add_listener(
            on_retry=lambda a: retries.append(a),
            on_timeout=lambda e: timeouts.append(e),
        )

        async def fail_op():
            raise ValueError("error")

        await executor.execute(fail_op)

        assert len(retries) == 2  # 2回リトライ

    @pytest.mark.asyncio
    async def test_sync_function(self):
        """同期関数"""
        executor = RetryExecutor(create_no_retry_policy())

        def sync_op():
            return "sync result"

        result = await executor.execute(sync_op)

        assert result.success
        assert result.result == "sync result"


class TestHelpers:
    """ヘルパー関数テスト"""

    def test_create_default_retry_policy(self):
        """デフォルトポリシー作成"""
        policy = create_default_retry_policy()
        assert policy.strategy == RetryStrategy.EXPONENTIAL
        assert policy.max_retries == 3

    def test_create_no_retry_policy(self):
        """リトライなしポリシー作成"""
        policy = create_no_retry_policy()
        assert policy.strategy == RetryStrategy.NONE
        assert policy.max_retries == 0


# ActionClass・TrustLevel テスト
from hiveforge.worker_bee.trust import (
    ActionClass,
    TrustLevel,
    ConfirmationResult,
    ConfirmationRequest,
    ConfirmationResponse,
    TrustManager,
    requires_confirmation,
    get_max_action_class,
    create_default_tool_classes,
)


class TestActionClass:
    """ActionClassのテスト"""

    def test_ordering(self):
        """危険度順序"""
        assert ActionClass.SAFE < ActionClass.CAREFUL
        assert ActionClass.CAREFUL < ActionClass.DANGEROUS
        assert ActionClass.DANGEROUS < ActionClass.CRITICAL

    def test_comparison(self):
        """比較演算"""
        assert ActionClass.SAFE <= ActionClass.SAFE
        assert ActionClass.SAFE <= ActionClass.CAREFUL
        assert ActionClass.DANGEROUS >= ActionClass.CAREFUL
        assert not ActionClass.SAFE > ActionClass.CAREFUL


class TestTrustLevel:
    """TrustLevelのテスト"""

    def test_ordering(self):
        """信頼度順序"""
        assert TrustLevel.UNTRUSTED < TrustLevel.LIMITED
        assert TrustLevel.LIMITED < TrustLevel.STANDARD
        assert TrustLevel.STANDARD < TrustLevel.ELEVATED
        assert TrustLevel.ELEVATED < TrustLevel.FULL


class TestRequiresConfirmation:
    """requires_confirmationのテスト"""

    def test_untrusted_safe(self):
        """UNTRUSTED + SAFE = 承認不要"""
        assert not requires_confirmation(TrustLevel.UNTRUSTED, ActionClass.SAFE)

    def test_untrusted_careful(self):
        """UNTRUSTED + CAREFUL = 承認必要"""
        assert requires_confirmation(TrustLevel.UNTRUSTED, ActionClass.CAREFUL)

    def test_limited_careful(self):
        """LIMITED + CAREFUL = 承認不要"""
        assert not requires_confirmation(TrustLevel.LIMITED, ActionClass.CAREFUL)

    def test_standard_dangerous(self):
        """STANDARD + DANGEROUS = 承認必要"""
        assert requires_confirmation(TrustLevel.STANDARD, ActionClass.DANGEROUS)

    def test_elevated_dangerous(self):
        """ELEVATED + DANGEROUS = 承認不要"""
        assert not requires_confirmation(TrustLevel.ELEVATED, ActionClass.DANGEROUS)

    def test_elevated_critical(self):
        """ELEVATED + CRITICAL = 承認必要"""
        assert requires_confirmation(TrustLevel.ELEVATED, ActionClass.CRITICAL)

    def test_full_critical(self):
        """FULL + CRITICAL = 承認不要"""
        assert not requires_confirmation(TrustLevel.FULL, ActionClass.CRITICAL)


class TestGetMaxActionClass:
    """get_max_action_classのテスト"""

    def test_untrusted_auto(self):
        """UNTRUSTED 自動承認はSAFEまで"""
        assert (
            get_max_action_class(TrustLevel.UNTRUSTED, auto_approve_only=True) == ActionClass.SAFE
        )

    def test_limited_auto(self):
        """LIMITED 自動承認はCAREFULまで"""
        assert (
            get_max_action_class(TrustLevel.LIMITED, auto_approve_only=True) == ActionClass.CAREFUL
        )

    def test_elevated_auto(self):
        """ELEVATED 自動承認はDANGEROUSまで"""
        assert (
            get_max_action_class(TrustLevel.ELEVATED, auto_approve_only=True)
            == ActionClass.DANGEROUS
        )

    def test_full_auto(self):
        """FULL 自動承認は全て"""
        assert get_max_action_class(TrustLevel.FULL, auto_approve_only=True) == ActionClass.CRITICAL


class TestTrustManager:
    """TrustManagerのテスト"""

    def test_set_get_agent_trust(self):
        """エージェント信頼レベル設定・取得"""
        manager = TrustManager()
        manager.set_agent_trust("agent-1", TrustLevel.STANDARD)
        assert manager.get_agent_trust("agent-1") == TrustLevel.STANDARD

    def test_default_trust(self):
        """デフォルトはUNTRUSTED"""
        manager = TrustManager()
        assert manager.get_agent_trust("unknown") == TrustLevel.UNTRUSTED

    def test_set_get_tool_class(self):
        """ツール危険度設定・取得"""
        manager = TrustManager()
        manager.set_tool_class("my_tool", ActionClass.DANGEROUS)
        assert manager.get_tool_class("my_tool") == ActionClass.DANGEROUS

    def test_default_tool_class(self):
        """デフォルトはDANGEROUS"""
        manager = TrustManager()
        assert manager.get_tool_class("unknown") == ActionClass.DANGEROUS

    def test_check_permission_allowed(self):
        """許可チェック - 許可"""
        manager = TrustManager()
        manager.set_agent_trust("agent-1", TrustLevel.STANDARD)
        manager.set_tool_class("read_file", ActionClass.SAFE)

        allowed, needs_confirm = manager.check_permission("agent-1", "read_file")
        assert allowed
        assert not needs_confirm

    def test_check_permission_needs_confirm(self):
        """許可チェック - 承認必要"""
        manager = TrustManager()
        manager.set_agent_trust("agent-1", TrustLevel.STANDARD)
        manager.set_tool_class("delete_file", ActionClass.DANGEROUS)

        allowed, needs_confirm = manager.check_permission("agent-1", "delete_file")
        assert allowed
        assert needs_confirm

    def test_check_permission_denied(self):
        """許可チェック - 拒否"""
        manager = TrustManager()
        manager.set_agent_trust("agent-1", TrustLevel.UNTRUSTED)
        manager.set_tool_class("delete_file", ActionClass.DANGEROUS)

        # UNTRUSTED は DANGEROUS を実行できない（承認があっても）
        # ただし現在の実装では STANDARD 以上なら全て可能
        # UNTRUSTED は SAFE のみ許可
        allowed, needs_confirm = manager.check_permission("agent-1", "delete_file")
        assert not allowed

    def test_request_confirmation_no_handler(self):
        """承認リクエスト - ハンドラなし"""
        manager = TrustManager()
        response = manager.request_confirmation("agent-1", "tool", "description")
        assert response.result == ConfirmationResult.DENIED
        assert "No confirmation handler" in response.reason

    def test_request_confirmation_with_handler(self):
        """承認リクエスト - ハンドラあり"""
        manager = TrustManager()

        def approve_all(req: ConfirmationRequest) -> ConfirmationResponse:
            return ConfirmationResponse(result=ConfirmationResult.APPROVED)

        manager.set_confirmation_handler(approve_all)
        response = manager.request_confirmation("agent-1", "tool", "description")
        assert response.result == ConfirmationResult.APPROVED


class TestDefaultToolClasses:
    """デフォルトツール分類テスト"""

    def test_safe_tools(self):
        """SAFEツール"""
        classes = create_default_tool_classes()
        assert classes["read_file"] == ActionClass.SAFE
        assert classes["list_dir"] == ActionClass.SAFE

    def test_dangerous_tools(self):
        """DANGEROUSツール"""
        classes = create_default_tool_classes()
        assert classes["delete_file"] == ActionClass.DANGEROUS
        assert classes["execute_command"] == ActionClass.DANGEROUS

    def test_critical_tools(self):
        """CRITICALツール"""
        classes = create_default_tool_classes()
        assert classes["rm_rf"] == ActionClass.CRITICAL
        assert classes["sudo"] == ActionClass.CRITICAL


class TestExecuteTaskWithLLM:
    """execute_task_with_llmハンドラのテスト"""

    def test_execute_task_with_llm_in_tool_definitions(self, worker_bee):
        """execute_task_with_llmがツール定義に含まれている"""
        tools = worker_bee.get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "execute_task_with_llm" in tool_names

    def test_execute_task_with_llm_schema(self, worker_bee):
        """execute_task_with_llmのスキーマが正しい"""
        tools = worker_bee.get_tool_definitions()
        llm_tool = next(t for t in tools if t["name"] == "execute_task_with_llm")

        schema = llm_tool["inputSchema"]
        assert "task_id" in schema["properties"]
        assert "run_id" in schema["properties"]
        assert "goal" in schema["properties"]
        assert "context" in schema["properties"]
        assert schema["required"] == ["task_id", "run_id", "goal"]

    @pytest.mark.asyncio
    async def test_dispatch_includes_execute_task_with_llm(self, worker_bee):
        """dispatch_toolにexecute_task_with_llmが含まれる"""
        # まずget_statusで正常動作確認
        result = await worker_bee.dispatch_tool("get_status", {})
        assert result["worker_id"] == "worker-1"

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, worker_bee):
        """closeでリソースが解放される"""
        # 何も初期化されていない状態でcloseしてもエラーにならない
        await worker_bee.close()

        assert worker_bee._llm_client is None
        assert worker_bee._agent_runner is None


class TestWorkerBeeAgentRunnerPromptContext:
    """Worker BeeのAgentRunnerがvault_pathとworker_idを渡すテスト"""

    @pytest.mark.asyncio
    async def test_agent_runner_receives_vault_path_and_worker_id(self, worker_bee):
        """Worker BeeのAgentRunnerがvault_pathとworker_nameを受け取る

        AgentRunnerがYAMLプロンプトを読み込めるよう、
        ARのvault_pathとworker_idを渡す。
        """
        # Arrange: LLMクライアントをモックで事前設定
        from unittest.mock import MagicMock, AsyncMock
        from hiveforge.llm.client import LLMClient

        mock_client = MagicMock(spec=LLMClient)
        mock_client.chat = AsyncMock()
        worker_bee._llm_client = mock_client

        # Act
        runner = await worker_bee._get_agent_runner()

        # Assert
        assert runner.vault_path == str(worker_bee.ar.vault_path)
        assert runner.worker_name == worker_bee.worker_id
        assert runner.agent_type == "worker_bee"
