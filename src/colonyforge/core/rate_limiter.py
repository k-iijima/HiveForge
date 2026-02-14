"""レートリミッター

LLM API呼び出しのレート制限を管理。
Token Bucket方式 + 並行リクエスト制限を実装。
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RateLimitStrategy(StrEnum):
    """レート制限戦略"""

    TOKEN_BUCKET = "token_bucket"  # トークンバケット方式
    SLIDING_WINDOW = "sliding_window"  # スライディングウィンドウ方式
    FIXED_WINDOW = "fixed_window"  # 固定ウィンドウ方式


@dataclass
class RateLimitConfig:
    """レート制限設定

    Default values are calibrated for OpenAI GPT-4-class models.
    Override via ``colonyforge.config.yaml`` ``llm.rate_limit`` section
    or by constructing a custom ``RateLimitConfig``.

    Attributes:
        requests_per_minute: Max requests per minute.
        requests_per_day: Max requests per day (0 = unlimited).
        tokens_per_minute: Max tokens per minute.
            Default 90 000 targets GPT-4 Tier-1.
        max_concurrent: Max concurrent in-flight requests.
        retry_after_429: Default back-off seconds on HTTP 429.
        burst_limit: Token-bucket burst capacity.
    """

    requests_per_minute: int = 60
    requests_per_day: int = 0  # 0 = unlimited
    tokens_per_minute: int = 90_000  # GPT-4 Tier-1 default; override per model/provider
    max_concurrent: int = 10
    retry_after_429: float = 60.0
    burst_limit: int = 10


@dataclass
class RateLimitState:
    """レート制限状態"""

    tokens: float = 0.0  # 現在のトークン数
    last_refill: float = field(default_factory=time.monotonic)
    request_count_minute: int = 0
    request_count_day: int = 0
    token_count_minute: int = 0
    minute_start: float = field(default_factory=time.monotonic)
    day_start: float = field(default_factory=time.monotonic)
    current_concurrent: int = 0


class RateLimiter:
    """レートリミッター

    Token Bucket方式でリクエストレートを制限。
    LLM API呼び出し時のレートリミット対策として使用。

    使用例:
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=60))

        async with limiter.acquire():
            response = await llm_client.chat(...)

        # または
        await limiter.wait()
        response = await llm_client.chat(...)
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self._config = config or RateLimitConfig()
        self._state = RateLimitState(tokens=float(self._config.burst_limit))
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent)
        self._waiters: list[asyncio.Event] = []

    @property
    def config(self) -> RateLimitConfig:
        """設定を取得"""
        return self._config

    def _refill_tokens(self) -> None:
        """トークンを補充（経過時間に応じて）"""
        now = time.monotonic()
        elapsed = now - self._state.last_refill

        # 1分あたりのリクエスト数からトークン補充レートを計算
        refill_rate = self._config.requests_per_minute / 60.0
        new_tokens = elapsed * refill_rate

        self._state.tokens = min(
            self._state.tokens + new_tokens,
            float(self._config.burst_limit),
        )
        self._state.last_refill = now

    def _reset_minute_window(self) -> None:
        """分単位のウィンドウをリセット"""
        now = time.monotonic()
        if now - self._state.minute_start >= 60.0:
            self._state.request_count_minute = 0
            self._state.token_count_minute = 0
            self._state.minute_start = now

    def _reset_day_window(self) -> None:
        """日単位のウィンドウをリセット"""
        now = time.monotonic()
        if now - self._state.day_start >= 86400.0:  # 24時間
            self._state.request_count_day = 0
            self._state.day_start = now

    async def wait(self, tokens: int = 1) -> None:
        """レート制限に従って待機

        ロックを保持したままsleepしないよう、待機時間の算出後にロックを
        解放してからsleepし、再取得して再チェックするループ構成。

        Args:
            tokens: 消費するトークン数（通常は1）

        Raises:
            RateLimitExceededError: 日次制限を超えた場合
        """
        while True:
            async with self._lock:
                self._reset_minute_window()
                self._reset_day_window()
                self._refill_tokens()

                # 日次制限チェック
                if (
                    self._config.requests_per_day > 0
                    and self._state.request_count_day >= self._config.requests_per_day
                ):
                    raise RateLimitExceededError(
                        "Daily request limit exceeded",
                        retry_after=self._seconds_until_day_reset(),
                    )

                # トークンが足りない場合は待機時間を計算
                if self._state.tokens < tokens:
                    wait_time = self._calculate_wait_time(tokens)
                else:
                    wait_time = 0.0

                if wait_time <= 0:
                    # トークン消費して終了
                    self._state.tokens -= tokens
                    self._state.request_count_minute += 1
                    self._state.request_count_day += 1
                    return

            # ロックを解放した状態でsleep
            await asyncio.sleep(wait_time)
            # ループ先頭でロック再取得・再チェック

    def _calculate_wait_time(self, tokens: int) -> float:
        """必要な待機時間を計算"""
        needed = tokens - self._state.tokens
        refill_rate = self._config.requests_per_minute / 60.0
        if refill_rate <= 0:
            return 0.0
        return needed / refill_rate

    def _seconds_until_day_reset(self) -> float:
        """日次リセットまでの秒数"""
        elapsed = time.monotonic() - self._state.day_start
        return max(0.0, 86400.0 - elapsed)

    async def acquire(self) -> "RateLimitContext":
        """レート制限コンテキストを取得

        async with構文で使用:
            async with limiter.acquire():
                await make_request()
        """
        await self.wait()
        await self._semaphore.acquire()
        self._state.current_concurrent += 1
        return RateLimitContext(self)

    def release(self) -> None:
        """並行リクエストスロットを解放"""
        self._semaphore.release()
        self._state.current_concurrent -= 1

    async def acquire_with_tokens(self, llm_tokens: int) -> "RateLimitContext":
        """LLMトークン数を考慮してレート制限を取得

        ロックを保持したままsleepしないよう、待機時間の算出後にロックを
        解放してからsleepし、再取得して再チェックするループ構成。

        Args:
            llm_tokens: LLM APIで使用するトークン数（推定）
        """
        wait_time = 0.0
        while True:
            async with self._lock:
                self._reset_minute_window()

                # トークン/分の制限チェック
                if self._state.token_count_minute + llm_tokens > self._config.tokens_per_minute:
                    wait_time = 60.0 - (time.monotonic() - self._state.minute_start)
                    if wait_time > 0:
                        # ロック外でsleepするためにbreakせずcontinue
                        pass
                    else:
                        self._reset_minute_window()
                        self._state.token_count_minute += llm_tokens
                        break
                else:
                    self._state.token_count_minute += llm_tokens
                    break

            # ロックを解放した状態でsleep
            await asyncio.sleep(wait_time)
            # ループ先頭でロック再取得・再チェック

        return await self.acquire()

    def get_stats(self) -> dict[str, Any]:
        """現在の統計を取得"""
        return {
            "tokens_available": self._state.tokens,
            "requests_this_minute": self._state.request_count_minute,
            "requests_today": self._state.request_count_day,
            "tokens_this_minute": self._state.token_count_minute,
            "current_concurrent": self._state.current_concurrent,
            "max_concurrent": self._config.max_concurrent,
        }

    async def handle_429(self, retry_after: float | None = None) -> None:
        """429エラー（Rate Limit）を処理

        Args:
            retry_after: Retry-Afterヘッダーの値（秒）
        """
        wait_time = retry_after or self._config.retry_after_429

        # トークンをゼロにリセット
        async with self._lock:
            self._state.tokens = 0.0

        await asyncio.sleep(wait_time)


class RateLimitContext:
    """レート制限コンテキストマネージャー"""

    def __init__(self, limiter: RateLimiter):
        self._limiter = limiter

    async def __aenter__(self) -> "RateLimitContext":
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        self._limiter.release()


class RateLimitExceededError(Exception):
    """レート制限超過例外"""

    def __init__(self, message: str, retry_after: float = 0.0):
        super().__init__(message)
        self.retry_after = retry_after


# --- モデル別のデフォルト設定 ---


def get_openai_rate_limit(model: str) -> RateLimitConfig:
    """OpenAIモデル別のレート制限設定を取得

    参考: https://platform.openai.com/docs/guides/rate-limits
    """
    # GPT-4系
    if model.startswith("gpt-4"):
        return RateLimitConfig(
            requests_per_minute=500,
            tokens_per_minute=30000,
            max_concurrent=10,
        )
    # GPT-3.5系
    elif model.startswith("gpt-3.5"):
        return RateLimitConfig(
            requests_per_minute=3500,
            tokens_per_minute=90000,
            max_concurrent=20,
        )
    # Default for unknown models — intentionally conservative.
    # Safe-side fallback: see AGENTS.md §3 (permitted case 1).
    return RateLimitConfig(
        requests_per_minute=60,
        tokens_per_minute=10_000,
        max_concurrent=5,
    )


def get_anthropic_rate_limit(tier: str = "1") -> RateLimitConfig:
    """Anthropic API Tier別のレート制限設定を取得

    参考: https://docs.anthropic.com/claude/reference/rate-limits
    """
    tiers = {
        "1": RateLimitConfig(
            requests_per_minute=50,
            tokens_per_minute=40000,
            max_concurrent=5,
        ),
        "2": RateLimitConfig(
            requests_per_minute=1000,
            tokens_per_minute=80000,
            max_concurrent=10,
        ),
        "3": RateLimitConfig(
            requests_per_minute=2000,
            tokens_per_minute=160000,
            max_concurrent=20,
        ),
        "4": RateLimitConfig(
            requests_per_minute=4000,
            tokens_per_minute=400000,
            max_concurrent=40,
        ),
    }
    return tiers.get(tier, tiers["1"])


# --- グローバルリミッター管理 ---


class RateLimiterRegistry:
    """レートリミッターのレジストリ

    複数のLLMプロバイダー/モデルを管理。
    """

    def __init__(self) -> None:
        self._limiters: dict[str, RateLimiter] = {}
        self._lock = asyncio.Lock()

    async def get_limiter(self, key: str, config: RateLimitConfig | None = None) -> RateLimiter:
        """リミッターを取得（なければ作成）"""
        async with self._lock:
            if key not in self._limiters:
                self._limiters[key] = RateLimiter(config)
            return self._limiters[key]

    async def get_for_openai(self, model: str) -> RateLimiter:
        """OpenAIモデル用リミッターを取得"""
        config = get_openai_rate_limit(model)
        return await self.get_limiter(f"openai:{model}", config)

    async def get_for_anthropic(self, tier: str = "1") -> RateLimiter:
        """Anthropic API用リミッターを取得"""
        config = get_anthropic_rate_limit(tier)
        return await self.get_limiter(f"anthropic:tier{tier}", config)

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """全リミッターの統計を取得"""
        return {key: limiter.get_stats() for key, limiter in self._limiters.items()}


# グローバルインスタンス
_global_registry: RateLimiterRegistry | None = None


def get_rate_limiter_registry() -> RateLimiterRegistry:
    """グローバルレジストリを取得"""
    global _global_registry
    if _global_registry is None:
        _global_registry = RateLimiterRegistry()
    return _global_registry
