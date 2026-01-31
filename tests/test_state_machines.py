"""状態機械のテスト"""

import pytest

from hiveforge.core.state import (
    RunStateMachine,
    TaskStateMachine,
    RequirementStateMachine,
    OscillationDetector,
    TransitionError,
    GovernanceError,
)
from hiveforge.core.ar.projections import RunState, TaskState, RequirementState
from hiveforge.core.events import (
    EventType,
    RunCompletedEvent,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskCreatedEvent,
    RequirementApprovedEvent,
)


class TestRunStateMachine:
    """RunStateMachineのテスト"""

    def test_initial_state(self):
        """初期状態はRUNNING"""
        sm = RunStateMachine()
        assert sm.current_state == RunState.RUNNING

    def test_complete_run(self):
        """Run完了遷移"""
        sm = RunStateMachine()
        event = RunCompletedEvent(run_id="test")

        new_state = sm.transition(event)
        assert new_state == RunState.COMPLETED

    def test_invalid_transition(self):
        """不正な遷移はエラー"""
        sm = RunStateMachine()
        sm.current_state = RunState.COMPLETED

        event = RunCompletedEvent(run_id="test")

        with pytest.raises(TransitionError):
            sm.transition(event)


class TestTaskStateMachine:
    """TaskStateMachineのテスト"""

    def test_initial_state(self):
        """初期状態はPENDING"""
        sm = TaskStateMachine()
        assert sm.current_state == TaskState.PENDING

    def test_assign_task(self):
        """タスク割り当て遷移"""
        sm = TaskStateMachine()
        event = TaskAssignedEvent(run_id="test", task_id="task-001")

        new_state = sm.transition(event)
        assert new_state == TaskState.IN_PROGRESS

    def test_complete_task(self):
        """タスク完了遷移"""
        sm = TaskStateMachine()
        sm.current_state = TaskState.IN_PROGRESS

        event = TaskCompletedEvent(run_id="test", task_id="task-001")
        new_state = sm.transition(event)

        assert new_state == TaskState.COMPLETED

    def test_fail_task(self):
        """タスク失敗遷移"""
        sm = TaskStateMachine()
        sm.current_state = TaskState.IN_PROGRESS

        event = TaskFailedEvent(run_id="test", task_id="task-001", payload={"error": "Error"})
        new_state = sm.transition(event)

        assert new_state == TaskState.FAILED

    def test_retry_count(self):
        """リトライカウント"""
        sm = TaskStateMachine(max_retries=3)

        # 失敗 -> リトライ を繰り返す
        for i in range(3):
            sm.current_state = TaskState.FAILED
            event = TaskCreatedEvent(run_id="test", task_id="task-001")
            sm.transition(event)
            assert sm.retry_count == i + 1

        # 4回目はリトライ不可
        sm.current_state = TaskState.FAILED
        assert not sm.can_retry()

    def test_get_valid_events(self):
        """有効なイベント一覧の取得"""
        sm = TaskStateMachine()
        sm.current_state = TaskState.IN_PROGRESS

        valid = sm.get_valid_events()
        assert EventType.TASK_BLOCKED in valid
        assert EventType.TASK_COMPLETED in valid
        assert EventType.TASK_FAILED in valid


class TestRequirementStateMachine:
    """RequirementStateMachineのテスト"""

    def test_initial_state(self):
        """初期状態はPENDING"""
        sm = RequirementStateMachine()
        assert sm.current_state == RequirementState.PENDING

    def test_approve_requirement(self):
        """要件承認遷移"""
        sm = RequirementStateMachine()
        event = RequirementApprovedEvent(run_id="test", payload={"requirement_id": "req-001"})

        new_state = sm.transition(event)
        assert new_state == RequirementState.APPROVED


class TestOscillationDetector:
    """OscillationDetectorのテスト"""

    def test_no_oscillation(self):
        """振動なし"""
        detector = OscillationDetector(max_oscillations=3)

        for state in [TaskState.PENDING, TaskState.IN_PROGRESS, TaskState.COMPLETED]:
            detector.record(state)

        assert detector.check() is True

    def test_detect_oscillation(self):
        """振動を検出"""
        detector = OscillationDetector(max_oscillations=3)

        # A-B-A-B-A-B パターン (3回の振動)
        for _ in range(3):
            detector.record(TaskState.IN_PROGRESS)
            detector.record(TaskState.BLOCKED)

        with pytest.raises(GovernanceError):
            detector.check()
