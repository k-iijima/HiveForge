"""状態機械 (State Machines)

Run, Task, Requirement の状態遷移を管理。
ガバナンス制約もここで強制。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ..ar.projections import ColonyState, HiveState, RequirementState, RunState, TaskState
from ..config import get_settings
from ..events import (
    BaseEvent,
    EventType,
)


class TransitionError(Exception):
    """不正な状態遷移"""

    pass


class GovernanceError(Exception):
    """ガバナンス制約違反"""

    pass


@dataclass
class Transition:
    """状態遷移の定義"""

    from_state: Enum
    to_state: Enum
    event_type: EventType
    guard: Callable[..., bool] | None = None


class StateMachine:
    """汎用状態機械基底クラス"""

    def __init__(self, initial_state: Enum, transitions: list[Transition]):
        self.current_state = initial_state
        self._transitions = {(t.from_state, t.event_type): t for t in transitions}

    def can_transition(self, event_type: EventType) -> bool:
        """指定イベントで遷移可能か確認"""
        return (self.current_state, event_type) in self._transitions

    def get_valid_events(self) -> list[EventType]:
        """現在の状態から遷移可能なイベント一覧を取得"""
        return [
            event_type for (state, event_type) in self._transitions if state == self.current_state
        ]

    def transition(self, event: BaseEvent) -> Enum:
        """イベントを適用して状態遷移

        Args:
            event: 適用するイベント

        Returns:
            遷移後の状態

        Raises:
            TransitionError: 不正な遷移の場合
        """
        key = (self.current_state, event.type)
        transition = self._transitions.get(key)

        if not transition:
            valid = self.get_valid_events()
            raise TransitionError(
                f"Invalid transition: {self.current_state} + {event.type}. Valid events: {valid}"
            )

        if transition.guard and not transition.guard(event):
            raise TransitionError(f"Guard condition failed for {event.type}")

        self.current_state = transition.to_state
        return self.current_state


class RunStateMachine(StateMachine):
    """Run状態機械

    状態遷移:
    - RUNNING -> COMPLETED (全タスク完了時)
    - RUNNING -> FAILED (致命的エラー時)
    - RUNNING -> ABORTED (ユーザー中断時または緊急停止時)
    """

    def __init__(self):
        transitions = [
            Transition(RunState.RUNNING, RunState.COMPLETED, EventType.RUN_COMPLETED),
            Transition(RunState.RUNNING, RunState.FAILED, EventType.RUN_FAILED),
            Transition(RunState.RUNNING, RunState.ABORTED, EventType.RUN_ABORTED),
            Transition(RunState.RUNNING, RunState.ABORTED, EventType.EMERGENCY_STOP),
        ]
        super().__init__(RunState.RUNNING, transitions)


class TaskStateMachine(StateMachine):
    """Task状態機械

    状態遷移:
    - PENDING -> IN_PROGRESS (割り当て時)
    - IN_PROGRESS -> BLOCKED (要件待ち時)
    - IN_PROGRESS -> COMPLETED (完了時)
    - IN_PROGRESS -> FAILED (失敗時)
    - BLOCKED -> IN_PROGRESS (ブロック解除時)
    - FAILED -> PENDING (リトライ時、回数制限あり)
    """

    def __init__(self, max_retries: int | None = None):
        self.retry_count = 0
        self.max_retries = max_retries or get_settings().governance.max_retries

        def retry_guard(event: BaseEvent) -> bool:
            return self.retry_count < self.max_retries

        transitions = [
            Transition(TaskState.PENDING, TaskState.IN_PROGRESS, EventType.TASK_ASSIGNED),
            Transition(TaskState.IN_PROGRESS, TaskState.BLOCKED, EventType.TASK_BLOCKED),
            Transition(TaskState.IN_PROGRESS, TaskState.COMPLETED, EventType.TASK_COMPLETED),
            Transition(TaskState.IN_PROGRESS, TaskState.FAILED, EventType.TASK_FAILED),
            Transition(TaskState.BLOCKED, TaskState.IN_PROGRESS, EventType.TASK_UNBLOCKED),
            # リトライ: FAILED -> PENDING (ガード付き)
            Transition(
                TaskState.FAILED, TaskState.PENDING, EventType.TASK_CREATED, guard=retry_guard
            ),
        ]
        super().__init__(TaskState.PENDING, transitions)

    def transition(self, event: BaseEvent) -> TaskState:
        """状態遷移（リトライカウント管理付き）"""
        old_state = self.current_state
        new_state = super().transition(event)

        # FAILED -> PENDING のリトライ時にカウントアップ
        if old_state == TaskState.FAILED and new_state == TaskState.PENDING:
            self.retry_count += 1

        return new_state  # type: ignore

    def can_retry(self) -> bool:
        """リトライ可能か確認"""
        return self.retry_count < self.max_retries


class RequirementStateMachine(StateMachine):
    """Requirement状態機械

    状態遷移:
    - PENDING -> APPROVED (承認時)
    - PENDING -> REJECTED (拒否時)
    """

    def __init__(self):
        transitions = [
            Transition(
                RequirementState.PENDING, RequirementState.APPROVED, EventType.REQUIREMENT_APPROVED
            ),
            Transition(
                RequirementState.PENDING, RequirementState.REJECTED, EventType.REQUIREMENT_REJECTED
            ),
        ]
        super().__init__(RequirementState.PENDING, transitions)


class OscillationDetector:
    """振動検出器

    同じ状態への遷移が繰り返される「振動」を検知。
    max_oscillations を超えた場合にエラーを発生。
    """

    def __init__(self, max_oscillations: int | None = None):
        self.max_oscillations = max_oscillations or get_settings().governance.max_oscillations
        self._state_history: list[Enum] = []

    def record(self, state: Enum) -> None:
        """状態を記録"""
        self._state_history.append(state)

    def check(self) -> bool:
        """振動が発生していないか確認

        Returns:
            True: 正常, False: 振動検知

        Raises:
            GovernanceError: 振動しきい値超過時
        """
        if len(self._state_history) < self.max_oscillations * 2:
            return True

        # 直近の状態で振動パターンを検出
        recent = self._state_history[-(self.max_oscillations * 2) :]

        # A-B-A-B... のようなパターンを検出
        if len(set(recent)) == 2:
            # 2つの状態が交互に出現していればエラー
            pattern_a = recent[0::2]  # 偶数インデックス
            pattern_b = recent[1::2]  # 奇数インデックス
            if len(set(pattern_a)) == 1 and len(set(pattern_b)) == 1:
                raise GovernanceError(
                    f"Oscillation detected: {recent}. Threshold: {self.max_oscillations}"
                )

        return True


class HiveStateMachine(StateMachine):
    """Hive状態機械

    Hiveは複数のColonyを管理する最上位コンテナ。

    状態遷移:
    - ACTIVE -> IDLE (全Colony完了時)
    - ACTIVE -> CLOSED (Hive終了時)
    - IDLE -> ACTIVE (新規Colony作成時)
    - IDLE -> CLOSED (Hive終了時)
    """

    def __init__(self):
        transitions = [
            # ACTIVE -> IDLE: 全Colony完了時
            Transition(HiveState.ACTIVE, HiveState.IDLE, EventType.COLONY_COMPLETED),
            # ACTIVE -> CLOSED: Hive終了時
            Transition(HiveState.ACTIVE, HiveState.CLOSED, EventType.HIVE_CLOSED),
            # IDLE -> ACTIVE: 新規Colony作成時
            Transition(HiveState.IDLE, HiveState.ACTIVE, EventType.COLONY_CREATED),
            # IDLE -> CLOSED: Hive終了時
            Transition(HiveState.IDLE, HiveState.CLOSED, EventType.HIVE_CLOSED),
        ]
        super().__init__(HiveState.ACTIVE, transitions)


class ColonyStateMachine(StateMachine):
    """Colony状態機械

    ColonyはHive内のサブプロジェクト単位。

    状態遷移:
    - PENDING -> IN_PROGRESS (開始時)
    - IN_PROGRESS -> COMPLETED (全Run完了時)
    - IN_PROGRESS -> FAILED (致命的エラー時)
    - IN_PROGRESS -> SUSPENDED (Sentinel Hornetによる強制停止)
    - SUSPENDED -> IN_PROGRESS (再開時)
    - SUSPENDED -> FAILED (失敗終了時)
    """

    def __init__(self):
        transitions = [
            # PENDING -> IN_PROGRESS: Colony開始時
            Transition(ColonyState.PENDING, ColonyState.IN_PROGRESS, EventType.COLONY_STARTED),
            # IN_PROGRESS -> COMPLETED: 全Run完了時
            Transition(ColonyState.IN_PROGRESS, ColonyState.COMPLETED, EventType.COLONY_COMPLETED),
            # IN_PROGRESS -> FAILED: 致命的エラー時
            Transition(ColonyState.IN_PROGRESS, ColonyState.FAILED, EventType.COLONY_FAILED),
            # IN_PROGRESS -> SUSPENDED: Sentinel Hornet強制停止
            Transition(ColonyState.IN_PROGRESS, ColonyState.SUSPENDED, EventType.COLONY_SUSPENDED),
            # SUSPENDED -> IN_PROGRESS: 再開
            Transition(ColonyState.SUSPENDED, ColonyState.IN_PROGRESS, EventType.COLONY_STARTED),
            # SUSPENDED -> FAILED: 失敗終了
            Transition(ColonyState.SUSPENDED, ColonyState.FAILED, EventType.COLONY_FAILED),
        ]
        super().__init__(ColonyState.PENDING, transitions)
