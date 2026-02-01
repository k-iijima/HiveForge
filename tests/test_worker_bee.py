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
