"""レートリミッターのテスト"""

import asyncio
import time

import pytest

from hiveforge.core.rate_limiter import (
    RateLimitConfig,
    RateLimitExceeded,
    RateLimiter,
    RateLimiterRegistry,
    get_anthropic_rate_limit,
    get_openai_rate_limit,
    get_rate_limiter_registry,
)


class TestRateLimitConfig:
    """RateLimitConfigのテスト"""

    def test_default_values(self):
        """デフォルト値が正しく設定される"""
        # Arrange & Act
        config = RateLimitConfig()

        # Assert
        assert config.requests_per_minute == 60
        assert config.requests_per_day == 0  # 無制限
        assert config.tokens_per_minute == 90000
        assert config.max_concurrent == 10
        assert config.retry_after_429 == 60.0
        assert config.burst_limit == 10

    def test_custom_values(self):
        """カスタム値が正しく設定される"""
        # Arrange & Act
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_day=10000,
            tokens_per_minute=50000,
            max_concurrent=5,
        )

        # Assert
        assert config.requests_per_minute == 100
        assert config.requests_per_day == 10000
        assert config.tokens_per_minute == 50000
        assert config.max_concurrent == 5


class TestRateLimiter:
    """RateLimiterのテスト"""

    @pytest.mark.asyncio
    async def test_basic_wait(self):
        """基本的なwaitが動作する"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                burst_limit=10,
            )
        )

        # Act & Assert: 最初のリクエストは即座に通る
        start = time.monotonic()
        await limiter.wait()
        elapsed = time.monotonic() - start

        assert elapsed < 0.1  # ほぼ待機なし

    @pytest.mark.asyncio
    async def test_burst_limit(self):
        """バースト制限が動作する"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                burst_limit=3,
            )
        )

        # Act: バースト制限内のリクエスト
        for _ in range(3):
            await limiter.wait()

        # Assert: 統計を確認
        stats = limiter.get_stats()
        assert stats["requests_this_minute"] == 3

    @pytest.mark.asyncio
    async def test_concurrent_limit(self):
        """並行リクエスト制限が動作する"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=100,
                max_concurrent=2,
                burst_limit=100,
            )
        )

        acquired = []

        async def acquire_and_hold(delay: float):
            async with await limiter.acquire():
                acquired.append(time.monotonic())
                await asyncio.sleep(delay)

        # Act: 3つのリクエストを同時に開始
        tasks = [
            asyncio.create_task(acquire_and_hold(0.1)),
            asyncio.create_task(acquire_and_hold(0.1)),
            asyncio.create_task(acquire_and_hold(0.1)),
        ]
        await asyncio.gather(*tasks)

        # Assert: 2つは同時に開始、1つは待機後に開始
        assert len(acquired) == 3
        # 最初の2つは同時に開始（差が小さい）
        assert abs(acquired[0] - acquired[1]) < 0.05
        # 3つ目は少し遅れて開始
        assert acquired[2] - acquired[0] >= 0.08

    @pytest.mark.asyncio
    async def test_acquire_context_manager(self):
        """async withでacquireが使える"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                burst_limit=10,
            )
        )

        # Act & Assert
        async with await limiter.acquire():
            stats = limiter.get_stats()
            assert stats["current_concurrent"] == 1

        # コンテキスト終了後
        stats = limiter.get_stats()
        assert stats["current_concurrent"] == 0

    @pytest.mark.asyncio
    async def test_daily_limit(self):
        """日次制限が動作する"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=100,
                requests_per_day=3,
                burst_limit=10,
            )
        )

        # Act: 日次制限まで使用
        for _ in range(3):
            await limiter.wait()

        # Assert: 制限超過で例外
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.wait()

        assert "Daily request limit exceeded" in str(exc_info.value)
        assert exc_info.value.retry_after > 0

    @pytest.mark.asyncio
    async def test_handle_429(self):
        """429エラー処理が動作する"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                burst_limit=10,
            )
        )

        # トークンを消費
        for _ in range(5):
            await limiter.wait()

        initial_tokens = limiter.get_stats()["tokens_available"]

        # Act: 429処理（短い待機時間でテスト）
        await limiter.handle_429(retry_after=0.01)

        # Assert: トークンがゼロにリセットされた後、少し回復
        final_tokens = limiter.get_stats()["tokens_available"]
        # 0.01秒待機後なのでほぼ0に近い
        assert final_tokens < initial_tokens or final_tokens < 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """統計取得が動作する"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                max_concurrent=10,
                burst_limit=10,
            )
        )

        # Act
        await limiter.wait()
        stats = limiter.get_stats()

        # Assert
        assert "tokens_available" in stats
        assert "requests_this_minute" in stats
        assert "requests_today" in stats
        assert "current_concurrent" in stats
        assert stats["requests_this_minute"] == 1
        assert stats["requests_today"] == 1

    @pytest.mark.asyncio
    async def test_token_based_limiting(self):
        """LLMトークンベースの制限が動作する"""
        # Arrange
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_minute=100,
                tokens_per_minute=1000,
                burst_limit=100,
            )
        )

        # Act: トークン制限内
        ctx = await limiter.acquire_with_tokens(500)
        await ctx.__aexit__(None, None, None)

        stats = limiter.get_stats()
        assert stats["tokens_this_minute"] == 500


class TestModelSpecificConfigs:
    """モデル別設定のテスト"""

    def test_openai_gpt4_config(self):
        """GPT-4の設定が正しい"""
        # Act
        config = get_openai_rate_limit("gpt-4")

        # Assert
        assert config.requests_per_minute == 500
        assert config.tokens_per_minute == 30000
        assert config.max_concurrent == 10

    def test_openai_gpt4_turbo_config(self):
        """GPT-4-turboの設定が正しい"""
        # Act
        config = get_openai_rate_limit("gpt-4-turbo")

        # Assert
        assert config.requests_per_minute == 500

    def test_openai_gpt35_config(self):
        """GPT-3.5の設定が正しい"""
        # Act
        config = get_openai_rate_limit("gpt-3.5-turbo")

        # Assert
        assert config.requests_per_minute == 3500
        assert config.tokens_per_minute == 90000
        assert config.max_concurrent == 20

    def test_anthropic_tier1_config(self):
        """Anthropic Tier 1の設定が正しい"""
        # Act
        config = get_anthropic_rate_limit("1")

        # Assert
        assert config.requests_per_minute == 50
        assert config.tokens_per_minute == 40000
        assert config.max_concurrent == 5

    def test_anthropic_tier4_config(self):
        """Anthropic Tier 4の設定が正しい"""
        # Act
        config = get_anthropic_rate_limit("4")

        # Assert
        assert config.requests_per_minute == 4000
        assert config.tokens_per_minute == 400000
        assert config.max_concurrent == 40


class TestRateLimiterRegistry:
    """RateLimiterRegistryのテスト"""

    @pytest.mark.asyncio
    async def test_get_limiter_creates_new(self):
        """存在しないリミッターは新規作成される"""
        # Arrange
        registry = RateLimiterRegistry()

        # Act
        limiter = await registry.get_limiter("test-key")

        # Assert
        assert limiter is not None
        assert isinstance(limiter, RateLimiter)

    @pytest.mark.asyncio
    async def test_get_limiter_returns_same(self):
        """同じキーで同じリミッターが返される"""
        # Arrange
        registry = RateLimiterRegistry()

        # Act
        limiter1 = await registry.get_limiter("test-key")
        limiter2 = await registry.get_limiter("test-key")

        # Assert
        assert limiter1 is limiter2

    @pytest.mark.asyncio
    async def test_get_for_openai(self):
        """OpenAI用リミッターが正しく取得される"""
        # Arrange
        registry = RateLimiterRegistry()

        # Act
        limiter = await registry.get_for_openai("gpt-4")

        # Assert
        assert limiter.config.requests_per_minute == 500

    @pytest.mark.asyncio
    async def test_get_for_anthropic(self):
        """Anthropic用リミッターが正しく取得される"""
        # Arrange
        registry = RateLimiterRegistry()

        # Act
        limiter = await registry.get_for_anthropic("2")

        # Assert
        assert limiter.config.requests_per_minute == 1000

    @pytest.mark.asyncio
    async def test_get_all_stats(self):
        """全リミッターの統計が取得できる"""
        # Arrange
        registry = RateLimiterRegistry()
        await registry.get_limiter("key1")
        await registry.get_limiter("key2")

        # Act
        stats = registry.get_all_stats()

        # Assert
        assert "key1" in stats
        assert "key2" in stats


class TestGlobalRegistry:
    """グローバルレジストリのテスト"""

    def test_get_global_registry(self):
        """グローバルレジストリが取得できる"""
        # Act
        registry = get_rate_limiter_registry()

        # Assert
        assert registry is not None
        assert isinstance(registry, RateLimiterRegistry)

    def test_global_registry_singleton(self):
        """グローバルレジストリはシングルトン"""
        # Act
        registry1 = get_rate_limiter_registry()
        registry2 = get_rate_limiter_registry()

        # Assert
        assert registry1 is registry2
