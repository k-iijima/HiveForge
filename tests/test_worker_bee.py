"""Worker Bee MCPサーバーのテスト"""

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
        result = await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Implement feature X",
        })

        # Assert
        assert result["status"] == "accepted"
        assert result["task_id"] == "task-1"
        assert worker_bee.state == WorkerState.WORKING

    @pytest.mark.asyncio
    async def test_receive_task_while_working(self, worker_bee):
        """作業中に別タスクは受け取れない"""
        # Arrange: まず1つ目のタスクを受け取る
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "First task",
        })

        # Act: 2つ目のタスクを受け取ろうとする
        result = await worker_bee.handle_receive_task({
            "task_id": "task-2",
            "run_id": "run-1",
            "goal": "Second task",
        })

        # Assert
        assert "error" in result
        assert result["current_task_id"] == "task-1"

    @pytest.mark.asyncio
    async def test_receive_task_emits_event(self, worker_bee, ar):
        """タスク受け取り時にイベントが発行される"""
        # Act
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test goal",
        })

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
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })

        # Act
        result = await worker_bee.handle_report_progress({
            "progress": 50,
            "message": "halfway done",
        })

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
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })

        # Act
        await worker_bee.handle_report_progress({
            "progress": 75,
            "message": "Almost done",
        })

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
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })

        # Act
        result = await worker_bee.handle_complete_task({
            "result": "Feature implemented",
            "deliverables": ["file1.py", "file2.py"],
        })

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
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })

        # Act
        await worker_bee.handle_complete_task({
            "result": "Success",
        })

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
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })

        # Act
        result = await worker_bee.handle_fail_task({
            "reason": "Connection timeout",
            "recoverable": True,
        })

        # Assert
        assert result["status"] == "failed"
        assert result["reason"] == "Connection timeout"
        assert result["recoverable"] is True
        assert worker_bee.state == WorkerState.IDLE

    @pytest.mark.asyncio
    async def test_fail_task_not_recoverable(self, worker_bee):
        """リカバリ不能な失敗はERROR状態になる"""
        # Arrange
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })

        # Act
        await worker_bee.handle_fail_task({
            "reason": "Fatal error",
            "recoverable": False,
        })

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
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })

        # Act
        await worker_bee.handle_fail_task({
            "reason": "Test failure",
        })

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
        await worker_bee.handle_receive_task({
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })
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
        result = await worker_bee.dispatch_tool("receive_task", {
            "task_id": "task-1",
            "run_id": "run-1",
            "goal": "Test",
        })
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
        pool.workers["worker-1"] = WorkerProjection(
            worker_id="worker-1", state="idle"
        )

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
