"""Tests for rate limiting module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from insights_agent.ratelimit import (
    TIER_LIMITS,
    RateLimits,
    RateLimitStatus,
    SubscriptionTier,
    get_limits_for_plan,
    get_limits_for_tier,
    get_tier_for_plan,
)


class TestSubscriptionTiers:
    """Tests for subscription tier configuration."""

    def test_tier_limits_defined(self):
        """Test that all tiers have limits defined."""
        for tier in SubscriptionTier:
            assert tier in TIER_LIMITS

    def test_tier_limits_structure(self):
        """Test that tier limits have correct structure."""
        for _tier, limits in TIER_LIMITS.items():
            assert isinstance(limits, RateLimits)
            assert limits.requests_per_minute > 0
            assert limits.requests_per_hour > 0
            assert limits.tokens_per_day > 0
            assert limits.concurrent_requests > 0

    def test_tier_limits_ordering(self):
        """Test that higher tiers have higher limits."""
        tiers = [
            SubscriptionTier.FREE,
            SubscriptionTier.BASIC,
            SubscriptionTier.PROFESSIONAL,
            SubscriptionTier.ENTERPRISE,
        ]

        for i in range(len(tiers) - 1):
            lower_limits = TIER_LIMITS[tiers[i]]
            higher_limits = TIER_LIMITS[tiers[i + 1]]

            assert higher_limits.requests_per_minute >= lower_limits.requests_per_minute
            assert higher_limits.requests_per_hour >= lower_limits.requests_per_hour
            assert higher_limits.tokens_per_day >= lower_limits.tokens_per_day


class TestPlanMapping:
    """Tests for plan to tier mapping."""

    def test_get_tier_for_plan_free(self):
        """Test free tier plan mapping."""
        assert get_tier_for_plan("free") == SubscriptionTier.FREE
        assert get_tier_for_plan("trial") == SubscriptionTier.FREE
        assert get_tier_for_plan(None) == SubscriptionTier.FREE

    def test_get_tier_for_plan_basic(self):
        """Test basic tier plan mapping."""
        assert get_tier_for_plan("basic") == SubscriptionTier.BASIC
        assert get_tier_for_plan("starter") == SubscriptionTier.BASIC

    def test_get_tier_for_plan_professional(self):
        """Test professional tier plan mapping."""
        assert get_tier_for_plan("professional") == SubscriptionTier.PROFESSIONAL
        assert get_tier_for_plan("pro") == SubscriptionTier.PROFESSIONAL
        assert get_tier_for_plan("standard") == SubscriptionTier.PROFESSIONAL

    def test_get_tier_for_plan_enterprise(self):
        """Test enterprise tier plan mapping."""
        assert get_tier_for_plan("enterprise") == SubscriptionTier.ENTERPRISE
        assert get_tier_for_plan("premium") == SubscriptionTier.ENTERPRISE
        assert get_tier_for_plan("unlimited") == SubscriptionTier.ENTERPRISE

    def test_get_tier_for_plan_case_insensitive(self):
        """Test that plan mapping is case insensitive."""
        assert get_tier_for_plan("ENTERPRISE") == SubscriptionTier.ENTERPRISE
        assert get_tier_for_plan("Professional") == SubscriptionTier.PROFESSIONAL

    def test_get_tier_for_unknown_plan(self):
        """Test that unknown plans default to free tier."""
        assert get_tier_for_plan("unknown") == SubscriptionTier.FREE
        assert get_tier_for_plan("custom-plan") == SubscriptionTier.FREE


class TestLimitsLookup:
    """Tests for limits lookup functions."""

    def test_get_limits_for_tier(self):
        """Test getting limits by tier."""
        limits = get_limits_for_tier(SubscriptionTier.PROFESSIONAL)

        assert limits.requests_per_minute == 60
        assert limits.requests_per_hour == 1000
        assert limits.tokens_per_day == 100_000
        assert limits.concurrent_requests == 10

    def test_get_limits_for_plan(self):
        """Test getting limits by plan name."""
        limits = get_limits_for_plan("enterprise")

        assert limits.requests_per_minute == 300
        assert limits.requests_per_hour == 10_000
        assert limits.tokens_per_day == 1_000_000
        assert limits.concurrent_requests == 50


class TestRateLimitStatus:
    """Tests for RateLimitStatus model."""

    def test_status_not_limited(self):
        """Test status when not rate limited."""
        status = RateLimitStatus(
            order_id="order-123",
            tier=SubscriptionTier.PROFESSIONAL,
            requests_this_minute=5,
            requests_this_hour=100,
            tokens_today=50_000,
            concurrent_requests=2,
            requests_per_minute_limit=60,
            requests_per_hour_limit=1000,
            tokens_per_day_limit=100_000,
            concurrent_requests_limit=10,
            is_rate_limited=False,
        )

        assert not status.is_rate_limited
        assert status.retry_after_seconds is None
        assert status.limit_type is None

    def test_status_limited(self):
        """Test status when rate limited."""
        status = RateLimitStatus(
            order_id="order-123",
            tier=SubscriptionTier.FREE,
            requests_this_minute=10,
            requests_this_hour=100,
            tokens_today=5_000,
            concurrent_requests=2,
            requests_per_minute_limit=10,
            requests_per_hour_limit=100,
            tokens_per_day_limit=10_000,
            concurrent_requests_limit=2,
            is_rate_limited=True,
            retry_after_seconds=30,
            limit_type="minute",
        )

        assert status.is_rate_limited
        assert status.retry_after_seconds == 30
        assert status.limit_type == "minute"


class TestRateLimiterMocked:
    """Tests for RateLimiter with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis_mock = MagicMock()
        # Pipeline methods are sync (they queue commands), execute is async
        mock_pipeline = MagicMock()
        mock_pipeline.get = MagicMock(return_value=mock_pipeline)
        mock_pipeline.incr = MagicMock(return_value=mock_pipeline)
        mock_pipeline.incrby = MagicMock(return_value=mock_pipeline)
        mock_pipeline.expire = MagicMock(return_value=mock_pipeline)
        mock_pipeline.execute = AsyncMock(return_value=[5, 100, 500, 2, 10000])
        redis_mock.pipeline = MagicMock(return_value=mock_pipeline)
        return redis_mock, mock_pipeline

    @pytest.mark.asyncio
    async def test_check_rate_limit_under_limit(self, mock_redis):
        """Test rate limit check when under limits."""
        from insights_agent.ratelimit.limiter import RateLimiter

        redis_mock, mock_pipeline = mock_redis

        limiter = RateLimiter()
        # Patch _get_redis to return our mock
        limiter._get_redis = AsyncMock(return_value=redis_mock)

        # Mock pipeline results (all under limits)
        mock_pipeline.execute = AsyncMock(return_value=[5, 100, 500, 2, 10000])

        status = await limiter.check_rate_limit("order-123", "professional")

        assert not status.is_rate_limited
        assert status.requests_this_minute == 5
        assert status.requests_this_hour == 100

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded_minute(self, mock_redis):
        """Test rate limit check when minute limit exceeded."""
        from insights_agent.ratelimit.limiter import RateLimiter

        redis_mock, mock_pipeline = mock_redis

        limiter = RateLimiter()
        limiter._get_redis = AsyncMock(return_value=redis_mock)

        # Mock pipeline results (minute limit exceeded)
        mock_pipeline.execute = AsyncMock(return_value=[60, 100, 500, 2, 10000])

        status = await limiter.check_rate_limit("order-123", "professional")

        assert status.is_rate_limited
        assert status.limit_type == "minute"
        assert status.retry_after_seconds is not None

    @pytest.mark.asyncio
    async def test_increment_request_count(self, mock_redis):
        """Test incrementing request counters."""
        from insights_agent.ratelimit.limiter import RateLimiter

        redis_mock, mock_pipeline = mock_redis

        limiter = RateLimiter()
        limiter._get_redis = AsyncMock(return_value=redis_mock)

        mock_pipeline.execute = AsyncMock(return_value=[1, True, 1, True, 1, True])

        await limiter.increment_request_count("order-123")

        # Verify pipeline was executed
        mock_pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_token_usage(self, mock_redis):
        """Test adding token usage."""
        from insights_agent.ratelimit.limiter import RateLimiter

        redis_mock, mock_pipeline = mock_redis

        limiter = RateLimiter()
        limiter._get_redis = AsyncMock(return_value=redis_mock)

        mock_pipeline.execute = AsyncMock(return_value=[1500, True])

        result = await limiter.add_token_usage("order-123", 500)

        assert result == 1500


class TestRateLimitService:
    """Tests for RateLimitService."""

    @pytest.fixture
    def mock_limiter(self):
        """Create mock rate limiter."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_check_and_enforce_allowed(self, mock_limiter):
        """Test check when request is allowed."""
        from insights_agent.ratelimit.service import RateLimitService

        mock_limiter.check_rate_limit = AsyncMock(
            return_value=RateLimitStatus(
                order_id="order-123",
                tier=SubscriptionTier.PROFESSIONAL,
                requests_this_minute=5,
                requests_this_hour=100,
                tokens_today=50_000,
                concurrent_requests=2,
                requests_per_minute_limit=60,
                requests_per_hour_limit=1000,
                tokens_per_day_limit=100_000,
                concurrent_requests_limit=10,
                is_rate_limited=False,
            )
        )

        service = RateLimitService(rate_limiter=mock_limiter)
        is_allowed, status = await service.check_and_enforce("order-123", "professional")

        assert is_allowed
        assert not status.is_rate_limited

    @pytest.mark.asyncio
    async def test_check_and_enforce_denied(self, mock_limiter):
        """Test check when request is denied."""
        from insights_agent.ratelimit.service import RateLimitService

        mock_limiter.check_rate_limit = AsyncMock(
            return_value=RateLimitStatus(
                order_id="order-123",
                tier=SubscriptionTier.FREE,
                requests_this_minute=10,
                requests_this_hour=100,
                tokens_today=5_000,
                concurrent_requests=2,
                requests_per_minute_limit=10,
                requests_per_hour_limit=100,
                tokens_per_day_limit=10_000,
                concurrent_requests_limit=2,
                is_rate_limited=True,
                retry_after_seconds=30,
                limit_type="minute",
            )
        )

        service = RateLimitService(rate_limiter=mock_limiter)
        is_allowed, status = await service.check_and_enforce("order-123", "free")

        assert not is_allowed
        assert status.is_rate_limited

    @pytest.mark.asyncio
    async def test_get_tier_info(self, mock_limiter):
        """Test getting tier information."""
        from insights_agent.ratelimit.service import RateLimitService

        service = RateLimitService(rate_limiter=mock_limiter)
        info = await service.get_tier_info("enterprise")

        assert info["tier"] == "enterprise"
        assert info["limits"]["requests_per_minute"] == 300
        assert info["limits"]["requests_per_hour"] == 10_000
