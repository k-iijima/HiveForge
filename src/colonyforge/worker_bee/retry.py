"""タイムアウト・リトライ機構

ツール実行のタイムアウト検出とリトライポリシー。
"""

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, TypeVar

from ulid import ULID

T = TypeVar("T")


class RetryStrategy(StrEnum):
    """リトライ戦略"""

    NONE = "none"  # リトライなし
    FIXED = "fixed"  # 固定間隔
    EXPONENTIAL = "exponential"  # 指数バックオフ
    LINEAR = "linear"  # 線形増加


class TimeoutBehavior(StrEnum):
    """タイムアウト時の振る舞い"""

    FAIL = "fail"  # 即失敗
    RETRY = "retry"  # リトライ
    ESCALATE = "escalate"  # エスカレート


@dataclass
class TimeoutConfig:
    """タイムアウト設定"""

    timeout_seconds: float = 30.0
    soft_timeout_seconds: float | None = None  # 警告タイムアウト
    behavior: TimeoutBehavior = TimeoutBehavior.FAIL


@dataclass
class RetryPolicy:
    """リトライポリシー"""

    strategy: RetryStrategy = RetryStrategy.FIXED
    max_retries: int = 3
    initial_delay: float = 1.0  # 秒
    max_delay: float = 60.0  # 秒
    multiplier: float = 2.0  # 指数バックオフ用
    jitter: bool = True  # ランダム揺らぎ
    retryable_errors: list[str] = field(default_factory=list)  # リトライ可能エラー

    def get_delay(self, attempt: int) -> float:
        """リトライ遅延を計算"""
        if self.strategy == RetryStrategy.NONE:
            return 0.0

        if self.strategy == RetryStrategy.FIXED:
            delay = self.initial_delay

        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.initial_delay * (self.multiplier**attempt)

        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.initial_delay * (attempt + 1)

        else:
            delay = self.initial_delay

        delay = min(delay, self.max_delay)

        if self.jitter:
            import random

            delay = delay * (0.5 + random.random())

        return delay

    def should_retry(self, error: str, attempt: int) -> bool:
        """リトライすべきか"""
        if self.strategy == RetryStrategy.NONE:
            return False

        if attempt >= self.max_retries:
            return False

        if self.retryable_errors:
            return any(e in error for e in self.retryable_errors)

        return True


@dataclass
class RetryAttempt:
    """リトライ試行"""

    attempt_id: str = field(default_factory=lambda: str(ULID()))
    attempt_number: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    success: bool = False
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class RetryResult:
    """リトライ結果"""

    result_id: str = field(default_factory=lambda: str(ULID()))
    success: bool = False
    result: Any = None
    error: str | None = None
    attempts: list[RetryAttempt] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def attempt_count(self) -> int:
        """試行回数"""
        return len(self.attempts)


class RetryExecutor:
    """リトライ実行器

    リトライポリシーに従って操作を再試行。
    """

    def __init__(self, policy: RetryPolicy | None = None):
        self._policy = policy or RetryPolicy()
        self._on_retry: list[Callable[[RetryAttempt], None]] = []
        self._on_timeout: list[Callable[[str], None]] = []

    def set_policy(self, policy: RetryPolicy) -> None:
        """ポリシー設定"""
        self._policy = policy

    def add_listener(
        self,
        on_retry: Callable[[RetryAttempt], None] | None = None,
        on_timeout: Callable[[str], None] | None = None,
    ) -> None:
        """リスナー追加"""
        if on_retry:
            self._on_retry.append(on_retry)
        if on_timeout:
            self._on_timeout.append(on_timeout)

    async def execute(
        self,
        operation: Callable[..., T],
        timeout_config: TimeoutConfig | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> RetryResult:
        """リトライ付き実行"""
        timeout = timeout_config or TimeoutConfig()
        result = RetryResult()
        start_time = datetime.now()

        for attempt_num in range(self._policy.max_retries + 1):
            attempt = RetryAttempt(attempt_number=attempt_num)

            try:
                # タイムアウト付き実行
                if asyncio.iscoroutinefunction(operation):
                    output = await asyncio.wait_for(
                        operation(*args, **kwargs),
                        timeout=timeout.timeout_seconds,
                    )
                else:
                    output = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: operation(*args, **kwargs)
                        ),
                        timeout=timeout.timeout_seconds,
                    )

                attempt.success = True
                attempt.ended_at = datetime.now()
                attempt.duration_ms = (attempt.ended_at - attempt.started_at).total_seconds() * 1000

                result.attempts.append(attempt)
                result.success = True
                result.result = output
                break

            except TimeoutError:
                attempt.error = f"Timeout after {timeout.timeout_seconds}s"
                attempt.ended_at = datetime.now()
                attempt.duration_ms = (attempt.ended_at - attempt.started_at).total_seconds() * 1000

                result.attempts.append(attempt)

                # タイムアウト通知
                for timeout_listener in self._on_timeout:
                    with contextlib.suppress(Exception):
                        timeout_listener(attempt.error)

                if timeout.behavior == TimeoutBehavior.FAIL:
                    result.error = attempt.error
                    break

                if not self._policy.should_retry(attempt.error, attempt_num):
                    result.error = attempt.error
                    break

            except Exception as e:
                attempt.error = str(e)
                attempt.ended_at = datetime.now()
                attempt.duration_ms = (attempt.ended_at - attempt.started_at).total_seconds() * 1000

                result.attempts.append(attempt)

                if not self._policy.should_retry(str(e), attempt_num):
                    result.error = str(e)
                    break

            # リトライ通知
            for retry_listener in self._on_retry:
                with contextlib.suppress(Exception):
                    retry_listener(attempt)

            # リトライ遅延
            delay = self._policy.get_delay(attempt_num)
            if delay > 0:
                await asyncio.sleep(delay)

        end_time = datetime.now()
        result.total_duration_ms = (end_time - start_time).total_seconds() * 1000

        return result

    async def execute_with_fallback(
        self,
        operation: Callable[..., T],
        fallback: Callable[..., T],
        timeout_config: TimeoutConfig | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> RetryResult:
        """フォールバック付き実行"""
        result = await self.execute(operation, timeout_config, *args, **kwargs)

        if not result.success:
            try:
                if asyncio.iscoroutinefunction(fallback):
                    fallback_result = await fallback(*args, **kwargs)
                else:
                    fallback_result = fallback(*args, **kwargs)

                result.result = fallback_result
                result.success = True
                result.error = None

            except Exception as e:
                result.error = f"Fallback failed: {e}"

        return result


def create_default_retry_policy() -> RetryPolicy:
    """デフォルトリトライポリシー"""
    return RetryPolicy(
        strategy=RetryStrategy.EXPONENTIAL,
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        multiplier=2.0,
        jitter=True,
    )


def create_no_retry_policy() -> RetryPolicy:
    """リトライなしポリシー"""
    return RetryPolicy(strategy=RetryStrategy.NONE, max_retries=0)
