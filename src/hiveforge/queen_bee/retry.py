"""Queen Bee リトライマネージャー

Worker Bee失敗時のリトライ戦略を管理する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RetryStrategy(str, Enum):
    """リトライ戦略"""

    NONE = "none"  # リトライしない
    SAME_WORKER = "same_worker"  # 同じWorkerでリトライ
    DIFFERENT_WORKER = "different_worker"  # 別Workerでリトライ
    ANY_WORKER = "any_worker"  # どのWorkerでもOK


@dataclass
class RetryPolicy:
    """リトライポリシー"""

    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.DIFFERENT_WORKER
    backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0


@dataclass
class TaskRetryState:
    """タスクのリトライ状態"""

    task_id: str
    attempt: int = 0
    failed_workers: list[str] = field(default_factory=list)
    last_error: str | None = None


@dataclass
class RetryManager:
    """リトライマネージャー

    失敗したタスクのリトライを管理する。
    """

    policy: RetryPolicy = field(default_factory=RetryPolicy)
    _retry_states: dict[str, TaskRetryState] = field(default_factory=dict)

    def record_failure(self, task_id: str, worker_id: str, error: str) -> None:
        """タスク失敗を記録"""
        if task_id not in self._retry_states:
            self._retry_states[task_id] = TaskRetryState(task_id=task_id)

        state = self._retry_states[task_id]
        state.attempt += 1
        state.failed_workers.append(worker_id)
        state.last_error = error

    def should_retry(self, task_id: str) -> bool:
        """リトライすべきかどうか"""
        if self.policy.strategy == RetryStrategy.NONE:
            return False

        state = self._retry_states.get(task_id)
        if not state:
            return True

        return state.attempt < self.policy.max_retries

    def get_retry_delay(self, task_id: str) -> float:
        """リトライまでの待機時間を取得"""
        state = self._retry_states.get(task_id)
        if not state:
            return self.policy.backoff_seconds

        # 指数バックオフ
        return self.policy.backoff_seconds * (self.policy.backoff_multiplier ** (state.attempt - 1))

    def get_excluded_workers(self, task_id: str) -> list[str]:
        """除外すべきWorker一覧を取得"""
        if self.policy.strategy == RetryStrategy.SAME_WORKER:
            return []  # 同じWorkerでリトライ = 除外なし

        state = self._retry_states.get(task_id)
        if not state:
            return []

        if self.policy.strategy == RetryStrategy.DIFFERENT_WORKER:
            return state.failed_workers

        return []  # ANY_WORKER = 除外なし

    def get_retry_state(self, task_id: str) -> TaskRetryState | None:
        """リトライ状態を取得"""
        return self._retry_states.get(task_id)

    def reset_task(self, task_id: str) -> None:
        """タスクのリトライ状態をリセット"""
        if task_id in self._retry_states:
            del self._retry_states[task_id]

    def get_attempt_count(self, task_id: str) -> int:
        """リトライ回数を取得"""
        state = self._retry_states.get(task_id)
        return state.attempt if state else 0

    def is_exhausted(self, task_id: str) -> bool:
        """リトライ回数を使い切ったか"""
        return not self.should_retry(task_id)
