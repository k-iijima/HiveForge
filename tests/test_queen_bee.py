"""Queen Bee タスクディスパッチャのテスト"""

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.core.events import EventType
from hiveforge.queen_bee import TaskDispatcher


@pytest.fixture
def ar(tmp_path):
    """テスト用Akashic Record"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def dispatcher(ar):
    """テスト用TaskDispatcher"""
    return TaskDispatcher(ar=ar)


class TestTaskDispatcher:
    """TaskDispatcherの基本テスト"""

    def test_register_worker(self, dispatcher):
        """Workerを登録できる"""
        # Act
        dispatcher.register_worker("worker-1")

        # Assert
        assert dispatcher.get_worker_count() == 1

    def test_unregister_worker(self, dispatcher):
        """Workerを登録解除できる"""
        # Arrange
        dispatcher.register_worker("worker-1")

        # Act
        dispatcher.unregister_worker("worker-1")

        # Assert
        assert dispatcher.get_worker_count() == 0

    def test_unregister_nonexistent_worker(self, dispatcher):
        """存在しないWorkerの解除は無視"""
        # Act & Assert: エラーにならない
        dispatcher.unregister_worker("nonexistent")

    def test_get_available_workers(self, dispatcher):
        """利用可能Workerを取得"""
        # Arrange
        dispatcher.register_worker("worker-1")
        dispatcher.register_worker("worker-2")

        # Act
        available = dispatcher.get_available_workers()

        # Assert
        assert len(available) == 2


class TestAssignTask:
    """assign_taskのテスト"""

    def test_assign_task_success(self, dispatcher):
        """タスクを正常に割り当てできる"""
        # Arrange
        dispatcher.register_worker("worker-1")

        # Act
        assignment = dispatcher.assign_task(
            task_id="task-1",
            run_id="run-1",
            goal="Implement feature X",
            context={"priority": "high"},
        )

        # Assert
        assert assignment is not None
        assert assignment.task_id == "task-1"
        assert assignment.worker_id == "worker-1"
        assert assignment.goal == "Implement feature X"

    def test_assign_task_no_worker(self, dispatcher):
        """Workerがいない場合はNone"""
        # Act
        assignment = dispatcher.assign_task(
            task_id="task-1",
            run_id="run-1",
            goal="Test",
        )

        # Assert
        assert assignment is None

    def test_assign_task_emits_event(self, dispatcher, ar):
        """タスク割り当て時にイベントが発行される"""
        # Arrange
        dispatcher.register_worker("worker-1")

        # Act
        dispatcher.assign_task(
            task_id="task-1",
            run_id="run-1",
            goal="Test goal",
        )

        # Assert
        events = list(ar.replay("run-1"))
        assert len(events) == 1
        assert events[0].type == EventType.WORKER_ASSIGNED
        assert events[0].worker_id == "worker-1"

    def test_assign_task_with_preferred_worker(self, dispatcher):
        """優先Workerを指定して割り当て"""
        # Arrange
        dispatcher.register_worker("worker-1")
        dispatcher.register_worker("worker-2")

        # Act
        assignment = dispatcher.assign_task(
            task_id="task-1",
            run_id="run-1",
            goal="Test",
            preferred_worker_id="worker-2",
        )

        # Assert
        assert assignment is not None
        assert assignment.worker_id == "worker-2"

    def test_assign_task_updates_worker_state(self, dispatcher):
        """割り当て後にWorker状態が更新される"""
        # Arrange
        dispatcher.register_worker("worker-1")

        # Act
        dispatcher.assign_task(
            task_id="task-1",
            run_id="run-1",
            goal="Test",
        )

        # Assert
        worker = dispatcher._worker_pool.get_worker("worker-1")
        assert worker is not None
        assert worker.current_task_id == "task-1"


class TestBulkAssign:
    """bulk_assignのテスト"""

    def test_bulk_assign_multiple_tasks(self, dispatcher):
        """複数タスクを一括割り当て"""
        # Arrange
        dispatcher.register_worker("worker-1")
        dispatcher.register_worker("worker-2")

        tasks = [
            {"task_id": "task-1", "goal": "Task 1"},
            {"task_id": "task-2", "goal": "Task 2"},
        ]

        # Act
        assignments = dispatcher.bulk_assign(tasks, run_id="run-1")

        # Assert
        assert len(assignments) == 2

    def test_bulk_assign_partial(self, dispatcher):
        """Workerが足りない場合は部分的に割り当て"""
        # Arrange
        dispatcher.register_worker("worker-1")

        tasks = [
            {"task_id": "task-1", "goal": "Task 1"},
            {"task_id": "task-2", "goal": "Task 2"},
        ]

        # Act
        assignments = dispatcher.bulk_assign(tasks, run_id="run-1")

        # Assert: 1つのみ割り当て成功
        assert len(assignments) == 1


class TestReassignTask:
    """reassign_taskのテスト"""

    def test_reassign_to_different_worker(self, dispatcher):
        """別のWorkerに再割り当て"""
        # Arrange
        dispatcher.register_worker("worker-1")
        dispatcher.register_worker("worker-2")

        # Act
        assignment = dispatcher.reassign_task(
            task_id="task-1",
            run_id="run-1",
            goal="Retry task",
            failed_worker_id="worker-1",
        )

        # Assert
        assert assignment is not None
        assert assignment.worker_id == "worker-2"

    def test_reassign_no_alternative(self, dispatcher):
        """代替Workerがない場合はNone"""
        # Arrange
        dispatcher.register_worker("worker-1")

        # Act
        assignment = dispatcher.reassign_task(
            task_id="task-1",
            run_id="run-1",
            goal="Retry",
            failed_worker_id="worker-1",
        )

        # Assert
        assert assignment is None


# Progress Collector テスト
from hiveforge.core.events import (
    WorkerAssignedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerProgressEvent,
    WorkerStartedEvent,
)
from hiveforge.queen_bee.progress import ProgressCollector, TaskProgress


class TestProgressCollector:
    """ProgressCollectorのテスト"""

    def test_update_from_assigned_event(self):
        """WORKER_ASSIGNEDイベントでタスク追跡開始"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="queen",
                payload={},
            )
        ]

        # Act
        collector.update_from_events(events)

        # Assert
        progress = collector.get_task_progress("task-1")
        assert progress is not None
        assert progress.status == "pending"

    def test_update_from_started_event(self):
        """WORKER_STARTEDイベントでin_progressに"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="queen",
                payload={},
            ),
            WorkerStartedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={},
            ),
        ]

        # Act
        collector.update_from_events(events)

        # Assert
        progress = collector.get_task_progress("task-1")
        assert progress is not None
        assert progress.status == "in_progress"

    def test_update_from_progress_event(self):
        """WORKER_PROGRESSイベントで進捗更新"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="queen",
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
        collector.update_from_events(events)

        # Assert
        progress = collector.get_task_progress("task-1")
        assert progress is not None
        assert progress.progress == 50

    def test_update_from_completed_event(self):
        """WORKER_COMPLETEDイベントで完了"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="queen",
                payload={},
            ),
            WorkerCompletedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                payload={"result": "Success!"},
            ),
        ]

        # Act
        collector.update_from_events(events)

        # Assert
        progress = collector.get_task_progress("task-1")
        assert progress is not None
        assert progress.status == "completed"
        assert progress.progress == 100
        assert progress.result == "Success!"

    def test_update_from_failed_event(self):
        """WORKER_FAILEDイベントで失敗"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="queen",
                payload={},
            ),
            WorkerFailedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                reason="Timeout",
                payload={},
            ),
        ]

        # Act
        collector.update_from_events(events)

        # Assert
        progress = collector.get_task_progress("task-1")
        assert progress is not None
        assert progress.status == "failed"
        assert progress.error == "Timeout"


class TestOverallProgress:
    """全体進捗計算のテスト"""

    def test_overall_progress_single_task(self):
        """単一タスクの全体進捗"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="queen",
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
        collector.update_from_events(events)

        # Assert
        assert collector.get_overall_progress() == 50

    def test_overall_progress_multiple_tasks(self):
        """複数タスクの全体進捗"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="queen", payload={},
            ),
            WorkerAssignedEvent(
                run_id="run-1", task_id="task-2", worker_id="worker-2",
                actor="queen", payload={},
            ),
            WorkerProgressEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="worker-1", progress=100, payload={},
            ),
            WorkerProgressEvent(
                run_id="run-1", task_id="task-2", worker_id="worker-2",
                actor="worker-2", progress=50, payload={},
            ),
        ]

        # Act
        collector.update_from_events(events)

        # Assert: (100 + 50) / 2 = 75
        assert collector.get_overall_progress() == 75

    def test_overall_progress_empty(self):
        """タスクがない場合は0%"""
        collector = ProgressCollector()
        assert collector.get_overall_progress() == 0


class TestCompletionStats:
    """完了統計のテスト"""

    def test_completion_stats(self):
        """完了統計を取得"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="queen", payload={},
            ),
            WorkerAssignedEvent(
                run_id="run-1", task_id="task-2", worker_id="worker-2",
                actor="queen", payload={},
            ),
            WorkerCompletedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="worker-1", payload={},
            ),
        ]

        # Act
        collector.update_from_events(events)
        stats = collector.get_completion_stats()

        # Assert
        assert stats["completed"] == 1
        assert stats["pending"] == 1

    def test_is_all_completed_true(self):
        """全完了チェック - 完了"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="queen", payload={},
            ),
            WorkerCompletedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="worker-1", payload={},
            ),
        ]

        # Act
        collector.update_from_events(events)

        # Assert
        assert collector.is_all_completed() is True

    def test_is_all_completed_false(self):
        """全完了チェック - 未完了"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="queen", payload={},
            ),
        ]

        # Act
        collector.update_from_events(events)

        # Assert
        assert collector.is_all_completed() is False

    def test_is_all_completed_empty(self):
        """タスクなしは未完了"""
        collector = ProgressCollector()
        assert collector.is_all_completed() is False

    def test_get_failed_tasks(self):
        """失敗タスク一覧を取得"""
        # Arrange
        collector = ProgressCollector()
        events = [
            WorkerAssignedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="queen", payload={},
            ),
            WorkerFailedEvent(
                run_id="run-1", task_id="task-1", worker_id="worker-1",
                actor="worker-1", reason="Error", payload={},
            ),
        ]

        # Act
        collector.update_from_events(events)
        failed = collector.get_failed_tasks()

        # Assert
        assert len(failed) == 1
        assert failed[0].task_id == "task-1"


# Retry Manager テスト
from hiveforge.queen_bee.retry import (
    RetryManager,
    RetryPolicy,
    RetryStrategy,
)


class TestRetryManager:
    """RetryManagerのテスト"""

    def test_record_failure(self):
        """失敗を記録"""
        # Arrange
        manager = RetryManager()

        # Act
        manager.record_failure("task-1", "worker-1", "Timeout")

        # Assert
        state = manager.get_retry_state("task-1")
        assert state is not None
        assert state.attempt == 1
        assert "worker-1" in state.failed_workers
        assert state.last_error == "Timeout"

    def test_should_retry_default(self):
        """デフォルトでリトライ可能"""
        manager = RetryManager()
        assert manager.should_retry("task-1") is True

    def test_should_retry_after_failure(self):
        """失敗後もリトライ可能（max未満）"""
        manager = RetryManager()
        manager.record_failure("task-1", "worker-1", "Error")
        assert manager.should_retry("task-1") is True

    def test_should_retry_exhausted(self):
        """最大回数到達でリトライ不可"""
        manager = RetryManager(policy=RetryPolicy(max_retries=2))
        manager.record_failure("task-1", "worker-1", "Error 1")
        manager.record_failure("task-1", "worker-2", "Error 2")
        assert manager.should_retry("task-1") is False

    def test_should_retry_none_strategy(self):
        """NONE戦略ではリトライしない"""
        manager = RetryManager(policy=RetryPolicy(strategy=RetryStrategy.NONE))
        assert manager.should_retry("task-1") is False


class TestRetryDelay:
    """リトライ遅延のテスト"""

    def test_initial_delay(self):
        """初回は基本遅延"""
        manager = RetryManager(policy=RetryPolicy(backoff_seconds=1.0))
        assert manager.get_retry_delay("task-1") == 1.0

    def test_exponential_backoff(self):
        """指数バックオフ"""
        manager = RetryManager(
            policy=RetryPolicy(backoff_seconds=1.0, backoff_multiplier=2.0)
        )
        manager.record_failure("task-1", "worker-1", "Error")
        # 1回目失敗後: 1.0 * 2^0 = 1.0
        assert manager.get_retry_delay("task-1") == 1.0

        manager.record_failure("task-1", "worker-2", "Error")
        # 2回目失敗後: 1.0 * 2^1 = 2.0
        assert manager.get_retry_delay("task-1") == 2.0


class TestExcludedWorkers:
    """除外Worker取得のテスト"""

    def test_different_worker_strategy(self):
        """DIFFERENT_WORKER戦略で失敗Workerを除外"""
        manager = RetryManager(
            policy=RetryPolicy(strategy=RetryStrategy.DIFFERENT_WORKER)
        )
        manager.record_failure("task-1", "worker-1", "Error")

        excluded = manager.get_excluded_workers("task-1")
        assert "worker-1" in excluded

    def test_same_worker_strategy(self):
        """SAME_WORKER戦略では除外なし"""
        manager = RetryManager(
            policy=RetryPolicy(strategy=RetryStrategy.SAME_WORKER)
        )
        manager.record_failure("task-1", "worker-1", "Error")

        excluded = manager.get_excluded_workers("task-1")
        assert excluded == []

    def test_any_worker_strategy(self):
        """ANY_WORKER戦略では除外なし"""
        manager = RetryManager(
            policy=RetryPolicy(strategy=RetryStrategy.ANY_WORKER)
        )
        manager.record_failure("task-1", "worker-1", "Error")

        excluded = manager.get_excluded_workers("task-1")
        assert excluded == []


class TestRetryStateManagement:
    """リトライ状態管理のテスト"""

    def test_reset_task(self):
        """タスク状態をリセット"""
        manager = RetryManager()
        manager.record_failure("task-1", "worker-1", "Error")

        manager.reset_task("task-1")

        assert manager.get_retry_state("task-1") is None

    def test_get_attempt_count(self):
        """リトライ回数を取得"""
        manager = RetryManager()
        assert manager.get_attempt_count("task-1") == 0

        manager.record_failure("task-1", "worker-1", "Error")
        assert manager.get_attempt_count("task-1") == 1

    def test_is_exhausted(self):
        """リトライ使い切り判定"""
        manager = RetryManager(policy=RetryPolicy(max_retries=1))
        assert manager.is_exhausted("task-1") is False

        manager.record_failure("task-1", "worker-1", "Error")
        assert manager.is_exhausted("task-1") is True


# Colony Scheduler テスト
from hiveforge.queen_bee.scheduler import (
    ColonyPriority,
    ColonyScheduler,
)


class TestColonyScheduler:
    """ColonySchedulerの基本テスト"""

    def test_register_colony(self):
        """Colonyを登録"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("colony-1", priority=ColonyPriority.HIGH)

        colony = scheduler.get_colony("colony-1")
        assert colony is not None
        assert colony.priority == ColonyPriority.HIGH

    def test_unregister_colony(self):
        """Colonyを登録解除"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("colony-1")
        scheduler.unregister_colony("colony-1")

        assert scheduler.get_colony("colony-1") is None

    def test_set_priority(self):
        """優先度を変更"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("colony-1", priority=ColonyPriority.NORMAL)

        result = scheduler.set_priority("colony-1", ColonyPriority.CRITICAL)

        assert result is True
        assert scheduler.get_colony("colony-1").priority == ColonyPriority.CRITICAL

    def test_set_priority_nonexistent(self):
        """存在しないColonyの優先度変更はFalse"""
        scheduler = ColonyScheduler()
        result = scheduler.set_priority("nonexistent", ColonyPriority.HIGH)
        assert result is False


class TestColonyEnableDisable:
    """Colony有効/無効のテスト"""

    def test_enable_colony(self):
        """Colonyを有効化"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("colony-1")
        scheduler.disable_colony("colony-1")

        result = scheduler.enable_colony("colony-1")

        assert result is True
        assert scheduler.get_colony("colony-1").enabled is True

    def test_disable_colony(self):
        """Colonyを無効化"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("colony-1")

        result = scheduler.disable_colony("colony-1")

        assert result is True
        assert scheduler.get_colony("colony-1").enabled is False

    def test_get_active_colonies(self):
        """有効なColonyのみ取得"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("colony-1")
        scheduler.register_colony("colony-2")
        scheduler.disable_colony("colony-2")

        active = scheduler.get_active_colonies()

        assert len(active) == 1
        assert active[0].colony_id == "colony-1"


class TestWorkerAllocation:
    """Worker配分のテスト"""

    def test_allocate_single_colony(self):
        """単一Colonyへの配分"""
        scheduler = ColonyScheduler(total_workers=10)
        scheduler.register_colony("colony-1", max_workers=5)

        allocations = scheduler.allocate_workers()

        assert len(allocations) == 1
        assert allocations[0].colony_id == "colony-1"
        assert allocations[0].allocated_workers >= 1

    def test_allocate_multiple_colonies(self):
        """複数Colonyへの配分"""
        scheduler = ColonyScheduler(total_workers=10)
        scheduler.register_colony("colony-1", priority=ColonyPriority.HIGH)
        scheduler.register_colony("colony-2", priority=ColonyPriority.LOW)

        allocations = scheduler.allocate_workers()

        assert len(allocations) == 2
        # 高優先度が多くWorkerを得る
        high_alloc = next(a for a in allocations if a.colony_id == "colony-1")
        low_alloc = next(a for a in allocations if a.colony_id == "colony-2")
        assert high_alloc.allocated_workers >= low_alloc.allocated_workers

    def test_allocate_no_colonies(self):
        """Colony無しの場合は空"""
        scheduler = ColonyScheduler()
        allocations = scheduler.allocate_workers()
        assert allocations == []

    def test_allocate_respects_max_workers(self):
        """max_workersを超えない"""
        scheduler = ColonyScheduler(total_workers=100)
        scheduler.register_colony("colony-1", max_workers=3)

        allocations = scheduler.allocate_workers()

        assert allocations[0].allocated_workers <= 3


class TestExecutionOrder:
    """実行順序のテスト"""

    def test_execution_order_by_priority(self):
        """優先度順に並ぶ"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("low", priority=ColonyPriority.LOW)
        scheduler.register_colony("critical", priority=ColonyPriority.CRITICAL)
        scheduler.register_colony("normal", priority=ColonyPriority.NORMAL)

        order = scheduler.get_execution_order()

        assert order[0] == "critical"
        assert order[-1] == "low"


class TestPreemption:
    """プリエンプションのテスト"""

    def test_should_preempt_higher_priority(self):
        """高優先度が待機中ならプリエンプト"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("running", priority=ColonyPriority.LOW)
        scheduler.register_colony("waiting", priority=ColonyPriority.CRITICAL)

        result = scheduler.should_preempt("running", "waiting")

        assert result is True

    def test_should_not_preempt_lower_priority(self):
        """低優先度が待機中ならプリエンプトしない"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("running", priority=ColonyPriority.CRITICAL)
        scheduler.register_colony("waiting", priority=ColonyPriority.LOW)

        result = scheduler.should_preempt("running", "waiting")

        assert result is False

    def test_should_preempt_nonexistent(self):
        """存在しないColonyはFalse"""
        scheduler = ColonyScheduler()
        result = scheduler.should_preempt("nonexistent1", "nonexistent2")
        assert result is False


# Colony Communication テスト
from hiveforge.queen_bee.communication import (
    ColonyMessenger,
    MessagePriority,
    MessageType,
    ResourceConflict,
)


class TestColonyMessenger:
    """ColonyMessengerの基本テスト"""

    def test_register_and_send(self):
        """Colonyを登録してメッセージ送信"""
        messenger = ColonyMessenger()
        messenger.register_colony("colony-1")
        messenger.register_colony("colony-2")

        message_id = messenger.send(
            from_colony="colony-1",
            to_colony="colony-2",
            message_type=MessageType.NOTIFICATION,
            payload={"data": "test"},
        )

        assert message_id is not None
        assert messenger.pending_count("colony-2") == 1

    def test_receive(self):
        """メッセージを受信"""
        messenger = ColonyMessenger()
        messenger.register_colony("colony-1")
        messenger.register_colony("colony-2")
        messenger.send(
            from_colony="colony-1",
            to_colony="colony-2",
            message_type=MessageType.NOTIFICATION,
            payload={"data": "hello"},
        )

        msg = messenger.receive("colony-2")

        assert msg is not None
        assert msg.from_colony == "colony-1"
        assert msg.payload == {"data": "hello"}
        assert messenger.pending_count("colony-2") == 0

    def test_broadcast(self):
        """全Colonyにブロードキャスト"""
        messenger = ColonyMessenger()
        messenger.register_colony("sender")
        messenger.register_colony("receiver-1")
        messenger.register_colony("receiver-2")

        messenger.broadcast(
            from_colony="sender",
            message_type=MessageType.BROADCAST,
            payload={"event": "shutdown"},
        )

        assert messenger.pending_count("receiver-1") == 1
        assert messenger.pending_count("receiver-2") == 1
        assert messenger.pending_count("sender") == 0

    def test_priority_ordering(self):
        """優先度順にメッセージを取得"""
        messenger = ColonyMessenger()
        messenger.register_colony("sender")
        messenger.register_colony("receiver")

        # 低優先度を先に送信
        messenger.send(
            from_colony="sender",
            to_colony="receiver",
            message_type=MessageType.NOTIFICATION,
            payload={"order": "low"},
            priority=MessagePriority.LOW,
        )
        # 高優先度を後に送信
        messenger.send(
            from_colony="sender",
            to_colony="receiver",
            message_type=MessageType.NOTIFICATION,
            payload={"order": "urgent"},
            priority=MessagePriority.URGENT,
        )

        # 高優先度が先に来る
        msg1 = messenger.receive("receiver")
        msg2 = messenger.receive("receiver")

        assert msg1.payload["order"] == "urgent"
        assert msg2.payload["order"] == "low"


class TestRequestResponse:
    """リクエスト-レスポンスパターンのテスト"""

    def test_request_and_respond(self):
        """リクエストに対してレスポンス"""
        messenger = ColonyMessenger()
        messenger.register_colony("client")
        messenger.register_colony("server")

        # リクエスト送信
        messenger.request(
            from_colony="client",
            to_colony="server",
            payload={"query": "status"},
        )

        # サーバーがリクエストを受信
        request = messenger.receive("server")
        assert request.message_type == MessageType.REQUEST

        # レスポンス送信
        messenger.respond(request, {"status": "ok"})

        # クライアントがレスポンスを受信
        response = messenger.receive("client")
        assert response.message_type == MessageType.RESPONSE
        assert response.correlation_id == request.message_id
        assert response.payload == {"status": "ok"}


class TestResourceConflict:
    """リソース競合のテスト"""

    def test_acquire_resource(self):
        """リソースを取得"""
        conflict = ResourceConflict()

        result = conflict.try_acquire("file-1", "colony-1")

        assert result is True
        assert conflict.get_holder("file-1") == "colony-1"

    def test_acquire_already_held(self):
        """既に保持されているリソースは取得失敗"""
        conflict = ResourceConflict()
        conflict.try_acquire("file-1", "colony-1")

        result = conflict.try_acquire("file-1", "colony-2")

        assert result is False
        assert conflict.get_holder("file-1") == "colony-1"

    def test_release_and_transfer(self):
        """解放後に待機Colonyへ転送"""
        conflict = ResourceConflict()
        conflict.try_acquire("file-1", "colony-1")
        conflict.wait_for("file-1", "colony-2")

        next_holder = conflict.release("file-1", "colony-1")

        assert next_holder == "colony-2"
        assert conflict.get_holder("file-1") == "colony-2"


class TestDeadlockDetection:
    """デッドロック検出のテスト"""

    def test_no_deadlock(self):
        """デッドロックなし"""
        conflict = ResourceConflict()
        conflict.try_acquire("file-1", "colony-1")
        conflict.wait_for("file-1", "colony-2")

        result = conflict.is_deadlock(["colony-1", "colony-2"])

        assert result is False

    def test_deadlock_detected(self):
        """相互待ちのデッドロック検出"""
        conflict = ResourceConflict()
        # colony-1がfile-1を保持
        conflict.try_acquire("file-1", "colony-1")
        # colony-2がfile-2を保持
        conflict.try_acquire("file-2", "colony-2")
        # colony-1がfile-2を待機
        conflict.wait_for("file-2", "colony-1")
        # colony-2がfile-1を待機
        conflict.wait_for("file-1", "colony-2")

        result = conflict.is_deadlock(["colony-1", "colony-2"])

        assert result is True


# 追加テスト: カバレッジ改善
class TestMessengerEdgeCases:
    """Messengerエッジケースのテスト"""

    def test_receive_from_unregistered(self):
        """未登録Colonyからの受信はNone"""
        messenger = ColonyMessenger()
        result = messenger.receive("nonexistent")
        assert result is None

    def test_peek_from_unregistered(self):
        """未登録Colonyのpeekはnone"""
        messenger = ColonyMessenger()
        result = messenger.peek("nonexistent")
        assert result is None

    def test_pending_count_unregistered(self):
        """未登録Colonyのpending_countは0"""
        messenger = ColonyMessenger()
        result = messenger.pending_count("nonexistent")
        assert result == 0

    def test_unregister_colony(self):
        """Colony登録解除"""
        messenger = ColonyMessenger()
        messenger.register_colony("colony-1")
        messenger.unregister_colony("colony-1")
        assert messenger.pending_count("colony-1") == 0

    def test_send_to_unregistered(self):
        """未登録先へのsendは配信しない"""
        messenger = ColonyMessenger()
        messenger.register_colony("sender")
        message_id = messenger.send(
            from_colony="sender",
            to_colony="nonexistent",
            message_type=MessageType.NOTIFICATION,
            payload={},
        )
        assert message_id is not None  # IDは発行される

    def test_peek(self):
        """peekでメッセージを確認（取り出さない）"""
        messenger = ColonyMessenger()
        messenger.register_colony("sender")
        messenger.register_colony("receiver")
        messenger.send(
            from_colony="sender",
            to_colony="receiver",
            message_type=MessageType.NOTIFICATION,
            payload={"data": "test"},
        )

        msg = messenger.peek("receiver")
        assert msg is not None
        assert messenger.pending_count("receiver") == 1  # 取り出していない


class TestResourceConflictEdgeCases:
    """ResourceConflictエッジケースのテスト"""

    def test_release_not_held(self):
        """保持していないリソースの解放"""
        conflict = ResourceConflict()
        result = conflict.release("file-1", "colony-1")
        assert result is None

    def test_release_by_wrong_holder(self):
        """別Colonyが保持しているリソースの解放は無効"""
        conflict = ResourceConflict()
        conflict.try_acquire("file-1", "colony-1")
        result = conflict.release("file-1", "colony-2")
        assert result is None
        assert conflict.get_holder("file-1") == "colony-1"

    def test_wait_for_duplicate(self):
        """重複waitは無視"""
        conflict = ResourceConflict()
        conflict.try_acquire("file-1", "colony-1")
        conflict.wait_for("file-1", "colony-2")
        conflict.wait_for("file-1", "colony-2")  # 重複

        waiting = conflict.get_waiting("file-1")
        assert waiting.count("colony-2") == 1

    def test_get_waiting_empty(self):
        """待機がないリソース"""
        conflict = ResourceConflict()
        waiting = conflict.get_waiting("nonexistent")
        assert waiting == []

    def test_acquire_same_holder(self):
        """同じColonyが再取得（既に保持）"""
        conflict = ResourceConflict()
        conflict.try_acquire("file-1", "colony-1")
        result = conflict.try_acquire("file-1", "colony-1")
        assert result is True  # 再取得OK

    def test_release_clears_wait_queue(self):
        """待機キューが空になった後"""
        conflict = ResourceConflict()
        conflict.try_acquire("file-1", "colony-1")
        conflict.wait_for("file-1", "colony-2")
        conflict.release("file-1", "colony-1")  # colony-2に移譲
        conflict.release("file-1", "colony-2")  # 完全解放

        assert conflict.get_holder("file-1") is None


class TestSchedulerEdgeCases:
    """Schedulerエッジケースのテスト"""

    def test_enable_nonexistent(self):
        """存在しないColonyのenable"""
        scheduler = ColonyScheduler()
        result = scheduler.enable_colony("nonexistent")
        assert result is False

    def test_disable_nonexistent(self):
        """存在しないColonyのdisable"""
        scheduler = ColonyScheduler()
        result = scheduler.disable_colony("nonexistent")
        assert result is False

    def test_unregister_nonexistent(self):
        """存在しないColonyのunregister"""
        scheduler = ColonyScheduler()
        # エラーにならない
        scheduler.unregister_colony("nonexistent")

    def test_allocate_disabled_colony(self):
        """無効化されたColonyには配分しない"""
        scheduler = ColonyScheduler(total_workers=10)
        scheduler.register_colony("colony-1")
        scheduler.disable_colony("colony-1")

        allocations = scheduler.allocate_workers()
        assert len(allocations) == 0

    def test_execution_order_disabled(self):
        """無効Colonyは実行順序に含まれない"""
        scheduler = ColonyScheduler()
        scheduler.register_colony("colony-1")
        scheduler.register_colony("colony-2")
        scheduler.disable_colony("colony-2")

        order = scheduler.get_execution_order()
        assert "colony-2" not in order


# ProgressCollector追加テスト
class TestProgressCollectorEdgeCases:
    """ProgressCollectorエッジケースのテスト"""

    def test_get_failed_tasks_empty(self):
        """失敗タスクがない場合"""
        from hiveforge.queen_bee.progress import ProgressCollector

        collector = ProgressCollector()
        collector._task_progress["task-1"] = TaskProgress(
            task_id="task-1", worker_id="worker-1", status="completed", progress=100
        )

        failed = collector.get_failed_tasks()
        assert failed == []

    def test_overall_progress_with_completed(self):
        """完了タスクを含む進捗計算"""
        from hiveforge.queen_bee.progress import ProgressCollector

        collector = ProgressCollector()
        collector._task_progress["task-1"] = TaskProgress(
            task_id="task-1", worker_id="worker-1", status="completed", progress=100
        )
        collector._task_progress["task-2"] = TaskProgress(
            task_id="task-2", worker_id="worker-2", status="in_progress", progress=50
        )

        overall = collector.get_overall_progress()
        assert overall == 75  # (100 + 50) / 2
