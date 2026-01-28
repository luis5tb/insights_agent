"""Redis-based rate limiter using sliding window algorithm."""

import asyncio
import logging
import time

import redis.asyncio as redis

from insights_agent.config import Settings, get_settings
from insights_agent.ratelimit.models import (
    RateLimitExceeded,
    RateLimitStatus,
    get_limits_for_plan,
    get_tier_for_plan,
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis-based rate limiter with sliding window algorithm.

    Implements rate limiting for:
    - Requests per minute (sliding window)
    - Requests per hour (sliding window)
    - Tokens per day (counter with daily reset)
    - Concurrent requests (semaphore)
    """

    # Redis key prefixes
    KEY_PREFIX = "ratelimit"
    MINUTE_KEY = f"{KEY_PREFIX}:minute"
    HOUR_KEY = f"{KEY_PREFIX}:hour"
    DAY_KEY = f"{KEY_PREFIX}:day"
    CONCURRENT_KEY = f"{KEY_PREFIX}:concurrent"
    TOKENS_KEY = f"{KEY_PREFIX}:tokens"

    # Time windows in seconds
    MINUTE = 60
    HOUR = 3600
    DAY = 86400

    def __init__(self, settings: Settings | None = None):
        """Initialize rate limiter.

        Args:
            settings: Application settings.
        """
        self._settings = settings or get_settings()
        self._redis: redis.Redis | None = None
        self._lock = asyncio.Lock()

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection.

        Returns:
            Redis client.
        """
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    self._redis = redis.from_url(  # type: ignore[no-untyped-call]
                        self._settings.redis_url,
                        encoding="utf-8",
                        decode_responses=True,
                    )
        return self._redis

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _get_key(self, prefix: str, order_id: str, window: str = "") -> str:
        """Build Redis key.

        Args:
            prefix: Key prefix.
            order_id: Order/Entitlement ID.
            window: Optional window identifier.

        Returns:
            Redis key.
        """
        if window:
            return f"{prefix}:{order_id}:{window}"
        return f"{prefix}:{order_id}"

    def _get_window_start(self, window_seconds: int) -> int:
        """Get the start of the current time window.

        Args:
            window_seconds: Window size in seconds.

        Returns:
            Window start timestamp.
        """
        now = int(time.time())
        return now - (now % window_seconds)

    async def check_rate_limit(
        self,
        order_id: str,
        plan: str | None = None,
    ) -> RateLimitStatus:
        """Check if request is within rate limits.

        Args:
            order_id: Order/Entitlement ID.
            plan: Subscription plan name.

        Returns:
            Current rate limit status.
        """
        tier = get_tier_for_plan(plan)
        limits = get_limits_for_plan(plan)

        r = await self._get_redis()
        now = int(time.time())

        # Get current window identifiers
        minute_window = self._get_window_start(self.MINUTE)
        hour_window = self._get_window_start(self.HOUR)
        day_window = self._get_window_start(self.DAY)

        # Build keys
        minute_key = self._get_key(self.MINUTE_KEY, order_id, str(minute_window))
        hour_key = self._get_key(self.HOUR_KEY, order_id, str(hour_window))
        day_key = self._get_key(self.DAY_KEY, order_id, str(day_window))
        concurrent_key = self._get_key(self.CONCURRENT_KEY, order_id)
        tokens_key = self._get_key(self.TOKENS_KEY, order_id, str(day_window))

        # Get current counts using pipeline
        pipe = r.pipeline()
        pipe.get(minute_key)
        pipe.get(hour_key)
        pipe.get(day_key)
        pipe.get(concurrent_key)
        pipe.get(tokens_key)
        results = await pipe.execute()

        requests_minute = int(results[0] or 0)
        requests_hour = int(results[1] or 0)
        _requests_day = int(results[2] or 0)  # noqa: F841 - fetched for future use
        concurrent = int(results[3] or 0)
        tokens_today = int(results[4] or 0)

        # Check limits
        is_limited = False
        limit_type = None
        retry_after = None

        if requests_minute >= limits.requests_per_minute:
            is_limited = True
            limit_type = "minute"
            retry_after = self.MINUTE - (now % self.MINUTE)
        elif requests_hour >= limits.requests_per_hour:
            is_limited = True
            limit_type = "hour"
            retry_after = self.HOUR - (now % self.HOUR)
        elif concurrent >= limits.concurrent_requests:
            is_limited = True
            limit_type = "concurrent"
            retry_after = 5  # Suggest retry after 5 seconds
        elif tokens_today >= limits.tokens_per_day:
            is_limited = True
            limit_type = "tokens"
            retry_after = self.DAY - (now % self.DAY)

        return RateLimitStatus(
            order_id=order_id,
            tier=tier,
            requests_this_minute=requests_minute,
            requests_this_hour=requests_hour,
            tokens_today=tokens_today,
            concurrent_requests=concurrent,
            requests_per_minute_limit=limits.requests_per_minute,
            requests_per_hour_limit=limits.requests_per_hour,
            tokens_per_day_limit=limits.tokens_per_day,
            concurrent_requests_limit=limits.concurrent_requests,
            is_rate_limited=is_limited,
            retry_after_seconds=retry_after,
            limit_type=limit_type,
        )

    async def increment_request_count(
        self,
        order_id: str,
    ) -> None:
        """Increment request counters.

        Args:
            order_id: Order/Entitlement ID.
        """
        r = await self._get_redis()

        # Get current window identifiers
        minute_window = self._get_window_start(self.MINUTE)
        hour_window = self._get_window_start(self.HOUR)
        day_window = self._get_window_start(self.DAY)

        # Build keys
        minute_key = self._get_key(self.MINUTE_KEY, order_id, str(minute_window))
        hour_key = self._get_key(self.HOUR_KEY, order_id, str(hour_window))
        day_key = self._get_key(self.DAY_KEY, order_id, str(day_window))

        # Increment with expiry using pipeline
        pipe = r.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, self.MINUTE * 2)  # Keep for 2 windows
        pipe.incr(hour_key)
        pipe.expire(hour_key, self.HOUR * 2)
        pipe.incr(day_key)
        pipe.expire(day_key, self.DAY * 2)
        await pipe.execute()

    async def increment_concurrent(self, order_id: str) -> int:
        """Increment concurrent request counter.

        Args:
            order_id: Order/Entitlement ID.

        Returns:
            New concurrent count.
        """
        r = await self._get_redis()
        key = self._get_key(self.CONCURRENT_KEY, order_id)

        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 300)  # Auto-expire after 5 minutes (safety net)
        results = await pipe.execute()

        return int(results[0])

    async def decrement_concurrent(self, order_id: str) -> int:
        """Decrement concurrent request counter.

        Args:
            order_id: Order/Entitlement ID.

        Returns:
            New concurrent count.
        """
        r = await self._get_redis()
        key = self._get_key(self.CONCURRENT_KEY, order_id)

        count = await r.decr(key)
        # Ensure we don't go negative
        if count < 0:
            await r.set(key, 0)
            return 0
        return int(count)

    async def add_token_usage(
        self,
        order_id: str,
        token_count: int,
    ) -> int:
        """Add token usage to daily counter.

        Args:
            order_id: Order/Entitlement ID.
            token_count: Number of tokens used.

        Returns:
            New total token count for today.
        """
        r = await self._get_redis()
        day_window = self._get_window_start(self.DAY)
        key = self._get_key(self.TOKENS_KEY, order_id, str(day_window))

        pipe = r.pipeline()
        pipe.incrby(key, token_count)
        pipe.expire(key, self.DAY * 2)
        results = await pipe.execute()

        return int(results[0])

    async def get_token_usage(self, order_id: str) -> int:
        """Get current daily token usage.

        Args:
            order_id: Order/Entitlement ID.

        Returns:
            Token count for today.
        """
        r = await self._get_redis()
        day_window = self._get_window_start(self.DAY)
        key = self._get_key(self.TOKENS_KEY, order_id, str(day_window))

        result = await r.get(key)
        return int(result or 0)

    async def reset_limits(self, order_id: str) -> None:
        """Reset all rate limits for an order (admin function).

        Args:
            order_id: Order/Entitlement ID.
        """
        r = await self._get_redis()

        # Find and delete all keys for this order
        pattern = f"{self.KEY_PREFIX}:*:{order_id}:*"
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=pattern, count=100)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break

        # Also delete non-windowed keys
        concurrent_key = self._get_key(self.CONCURRENT_KEY, order_id)
        await r.delete(concurrent_key)

    def build_exceeded_response(
        self,
        status: RateLimitStatus,
    ) -> RateLimitExceeded:
        """Build rate limit exceeded response.

        Args:
            status: Current rate limit status.

        Returns:
            Rate limit exceeded response.
        """
        limit_type = status.limit_type or "unknown"

        # Get current and limit values based on type
        if limit_type == "minute":
            current = status.requests_this_minute
            limit = status.requests_per_minute_limit
            message = f"Rate limit exceeded: {current}/{limit} requests per minute"
        elif limit_type == "hour":
            current = status.requests_this_hour
            limit = status.requests_per_hour_limit
            message = f"Rate limit exceeded: {current}/{limit} requests per hour"
        elif limit_type == "tokens":
            current = status.tokens_today
            limit = status.tokens_per_day_limit
            message = f"Token limit exceeded: {current}/{limit} tokens per day"
        elif limit_type == "concurrent":
            current = status.concurrent_requests
            limit = status.concurrent_requests_limit
            message = f"Too many concurrent requests: {current}/{limit}"
        else:
            current = 0
            limit = 0
            message = "Rate limit exceeded"

        return RateLimitExceeded(
            message=message,
            limit_type=limit_type,
            limit=limit,
            current=current,
            retry_after=status.retry_after_seconds or 60,
            tier=status.tier,
        )


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance.

    Returns:
        RateLimiter instance.
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
