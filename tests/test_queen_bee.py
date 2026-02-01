"""Queen Bee タスクディスパッチャのテスト"""

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.core.events import EventType
from hiveforge.queen_bee import TaskDispatcher, TaskAssignment
from hiveforge.worker_bee.projections import WorkerState


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
from hiveforge.queen_bee.progress import ProgressCollector, TaskProgress
from hiveforge.core.events import (
    WorkerAssignedEvent,
    WorkerStartedEvent,
    WorkerProgressEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
)


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
    TaskRetryState,
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
