"""状態機械のテスト"""

import pytest

from hiveforge.core.ar.projections import RequirementState, RunState, TaskState
from hiveforge.core.events import (
    EventType,
    RequirementApprovedEvent,
    RunCompletedEvent,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
)
from hiveforge.core.state import (
    GovernanceError,
    OscillationDetector,
    RequirementStateMachine,
    RunStateMachine,
    TaskStateMachine,
    TransitionError,
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

    def test_retry_guard_prevents_transition_when_limit_exceeded(self):
        """リトライ上限を超えるとガード条件で遷移が拒否される

        max_retriesに達した後のリトライはTransitionErrorを発生させる。
        """
        # Arrange: max_retries=1の状態機械でリトライ上限に達する
        sm = TaskStateMachine(max_retries=1)
        sm.current_state = TaskState.FAILED
        sm.retry_count = 0

        # 最初のリトライは成功
        event = TaskCreatedEvent(run_id="test", task_id="task-001")
        sm.transition(event)
        assert sm.retry_count == 1

        # 再度失敗状態にする
        sm.current_state = TaskState.FAILED

        # Act & Assert: 2回目のリトライはガード条件により拒否される
        with pytest.raises(TransitionError, match="Guard condition failed"):
            sm.transition(TaskCreatedEvent(run_id="test", task_id="task-001"))

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

    def test_no_oscillation_with_three_or_more_states(self):
        """3種類以上の状態がある場合は振動とみなさない

        A-B-A-B パターンではなく A-B-C-D のようなパターンは
        十分なデータがあっても振動ではない。
        """
        # Arrange: max_oscillationsの2倍以上の状態を記録
        detector = OscillationDetector(max_oscillations=3)

        # Act: 3種類以上の状態を含むパターン
        states = [
            TaskState.PENDING,
            TaskState.IN_PROGRESS,
            TaskState.BLOCKED,
            TaskState.IN_PROGRESS,
            TaskState.COMPLETED,
            TaskState.FAILED,
        ]
        for state in states:
            detector.record(state)

        # Assert: 振動とはみなされない
        assert detector.check() is True

    def test_two_states_not_alternating_pattern(self):
        """2種類の状態でも交互パターンでなければ振動ではない

        例: A-A-B-B-A-B のように、連続した同じ状態が含まれる場合は
        厳密な交互パターン(A-B-A-B...)ではないため振動とみなさない。
        """
        # Arrange: max_oscillations=2の検出器
        detector = OscillationDetector(max_oscillations=2)

        # Act: 2種類の状態だが、交互パターンではない
        # A-A-B-B (4要素で max_oscillations*2 = 4)
        detector.record(TaskState.IN_PROGRESS)  # A
        detector.record(TaskState.IN_PROGRESS)  # A (連続)
        detector.record(TaskState.BLOCKED)  # B
        detector.record(TaskState.BLOCKED)  # B (連続)

        # Assert: 交互パターンではないので振動ではない
        assert detector.check() is True


class TestStateMachineCanTransition:
    """StateMachineのcan_transitionメソッドのテスト"""

    def test_can_transition_returns_true_for_valid_event(self):
        """有効なイベントに対してcan_transitionはTrueを返す"""
        # Arrange: RUNNING状態のRun状態機械
        sm = RunStateMachine()

        # Act & Assert: RUN_COMPLETEDは有効な遷移
        assert sm.can_transition(EventType.RUN_COMPLETED) is True

    def test_can_transition_returns_false_for_invalid_event(self):
        """無効なイベントに対してcan_transitionはFalseを返す"""
        # Arrange: RUNNING状態のRun状態機械
        sm = RunStateMachine()

        # Act & Assert: TASK_CREATEDはRunの遷移には無効
        assert sm.can_transition(EventType.TASK_CREATED) is False


class TestHiveStateMachine:
    """HiveStateMachineのテスト

    Hiveは複数のColonyを管理する最上位コンテナ。
    状態: ACTIVE -> IDLE -> CLOSED
    """

    def test_initial_state_is_active(self):
        """初期状態はACTIVE

        Hive作成直後は作業可能なACTIVE状態。
        """
        # Arrange: なし

        # Act: Hive状態機械を作成
        from hiveforge.core.ar.projections import HiveState
        from hiveforge.core.state import HiveStateMachine

        sm = HiveStateMachine()

        # Assert: 初期状態はACTIVE
        assert sm.current_state == HiveState.ACTIVE

    def test_transition_active_to_idle(self):
        """ACTIVE -> IDLE遷移

        全てのColonyが完了したときにIDLE状態に遷移。
        """
        # Arrange: ACTIVE状態のHive
        from hiveforge.core.ar.projections import HiveState
        from hiveforge.core.events import ColonyCompletedEvent
        from hiveforge.core.state import HiveStateMachine

        sm = HiveStateMachine()

        # Act: 最後のColony完了イベントを適用
        event = ColonyCompletedEvent(payload={"colony_id": "colony-001"})
        new_state = sm.transition(event)

        # Assert: IDLE状態に遷移
        assert new_state == HiveState.IDLE

    def test_transition_idle_to_active(self):
        """IDLE -> ACTIVE遷移

        新しいColonyが作成されたときにACTIVE状態に戻る。
        """
        # Arrange: IDLE状態のHive
        from hiveforge.core.ar.projections import HiveState
        from hiveforge.core.events import ColonyCreatedEvent
        from hiveforge.core.state import HiveStateMachine

        sm = HiveStateMachine()
        sm.current_state = HiveState.IDLE

        # Act: 新しいColony作成イベントを適用
        event = ColonyCreatedEvent(payload={"colony_id": "colony-002", "hive_id": "hive-001"})
        new_state = sm.transition(event)

        # Assert: ACTIVE状態に戻る
        assert new_state == HiveState.ACTIVE

    def test_transition_active_to_closed(self):
        """ACTIVE -> CLOSED遷移

        HiveがクローズされたときにCLOSED状態に遷移。
        """
        # Arrange: ACTIVE状態のHive
        from hiveforge.core.ar.projections import HiveState
        from hiveforge.core.events import HiveClosedEvent
        from hiveforge.core.state import HiveStateMachine

        sm = HiveStateMachine()

        # Act: Hive終了イベントを適用
        event = HiveClosedEvent(payload={"hive_id": "hive-001"})
        new_state = sm.transition(event)

        # Assert: CLOSED状態に遷移
        assert new_state == HiveState.CLOSED

    def test_transition_idle_to_closed(self):
        """IDLE -> CLOSED遷移

        待機中のHiveもクローズ可能。
        """
        # Arrange: IDLE状態のHive
        from hiveforge.core.ar.projections import HiveState
        from hiveforge.core.events import HiveClosedEvent
        from hiveforge.core.state import HiveStateMachine

        sm = HiveStateMachine()
        sm.current_state = HiveState.IDLE

        # Act: Hive終了イベントを適用
        event = HiveClosedEvent(payload={"hive_id": "hive-001"})
        new_state = sm.transition(event)

        # Assert: CLOSED状態に遷移
        assert new_state == HiveState.CLOSED

    def test_closed_state_is_terminal(self):
        """CLOSED状態からは遷移不可（終端状態）

        クローズされたHiveは再利用できない。
        """
        # Arrange: CLOSED状態のHive
        from hiveforge.core.ar.projections import HiveState
        from hiveforge.core.events import ColonyCreatedEvent
        from hiveforge.core.state import HiveStateMachine

        sm = HiveStateMachine()
        sm.current_state = HiveState.CLOSED

        # Act & Assert: いかなる遷移も失敗
        event = ColonyCreatedEvent(payload={"colony_id": "colony-001"})
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_get_valid_events_from_active(self):
        """ACTIVE状態から遷移可能なイベント一覧"""
        # Arrange: ACTIVE状態のHive
        from hiveforge.core.events import EventType
        from hiveforge.core.state import HiveStateMachine

        sm = HiveStateMachine()

        # Act: 有効なイベント一覧を取得
        valid_events = sm.get_valid_events()

        # Assert: colony.completed と hive.closed が有効
        assert EventType.COLONY_COMPLETED in valid_events
        assert EventType.HIVE_CLOSED in valid_events


class TestColonyStateMachine:
    """ColonyStateMachineのテスト

    ColonyはHive内のサブプロジェクト単位。
    状態: PENDING -> IN_PROGRESS -> COMPLETED/FAILED
    """

    def test_initial_state_is_pending(self):
        """初期状態はPENDING

        Colony作成直後は開始待ちのPENDING状態。
        """
        # Arrange: なし

        # Act: Colony状態機械を作成
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()

        # Assert: 初期状態はPENDING
        assert sm.current_state == ColonyState.PENDING

    def test_transition_pending_to_in_progress(self):
        """PENDING -> IN_PROGRESS遷移

        Colony開始時にIN_PROGRESS状態に遷移。
        """
        # Arrange: PENDING状態のColony
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import ColonyStartedEvent
        from hiveforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()

        # Act: Colony開始イベントを適用
        event = ColonyStartedEvent(payload={"colony_id": "colony-001"})
        new_state = sm.transition(event)

        # Assert: IN_PROGRESS状態に遷移
        assert new_state == ColonyState.IN_PROGRESS

    def test_transition_in_progress_to_completed(self):
        """IN_PROGRESS -> COMPLETED遷移

        全Run完了時にCOMPLETED状態に遷移。
        """
        # Arrange: IN_PROGRESS状態のColony
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import ColonyCompletedEvent
        from hiveforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.IN_PROGRESS

        # Act: Colony完了イベントを適用
        event = ColonyCompletedEvent(payload={"colony_id": "colony-001"})
        new_state = sm.transition(event)

        # Assert: COMPLETED状態に遷移
        assert new_state == ColonyState.COMPLETED

    def test_transition_in_progress_to_failed(self):
        """IN_PROGRESS -> FAILED遷移

        致命的エラー発生時にFAILED状態に遷移。
        """
        # Arrange: IN_PROGRESS状態のColony
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import ColonyFailedEvent
        from hiveforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.IN_PROGRESS

        # Act: Colony失敗イベントを適用
        event = ColonyFailedEvent(payload={"colony_id": "colony-001", "error": "Critical error"})
        new_state = sm.transition(event)

        # Assert: FAILED状態に遷移
        assert new_state == ColonyState.FAILED

    def test_completed_state_is_terminal(self):
        """COMPLETED状態からは遷移不可（終端状態）"""
        # Arrange: COMPLETED状態のColony
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import ColonyStartedEvent
        from hiveforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.COMPLETED

        # Act & Assert: いかなる遷移も失敗
        event = ColonyStartedEvent(payload={"colony_id": "colony-001"})
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_failed_state_is_terminal(self):
        """FAILED状態からは遷移不可（終端状態）"""
        # Arrange: FAILED状態のColony
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import ColonyStartedEvent
        from hiveforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.FAILED

        # Act & Assert: いかなる遷移も失敗
        event = ColonyStartedEvent(payload={"colony_id": "colony-001"})
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_get_valid_events_from_pending(self):
        """PENDING状態から遷移可能なイベント一覧"""
        # Arrange: PENDING状態のColony
        from hiveforge.core.events import EventType
        from hiveforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()

        # Act: 有効なイベント一覧を取得
        valid_events = sm.get_valid_events()

        # Assert: colony.started のみが有効
        assert EventType.COLONY_STARTED in valid_events
        assert len(valid_events) == 1
