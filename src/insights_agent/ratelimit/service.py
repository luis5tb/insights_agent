"""Rate limiting service with subscription tier integration."""

import logging
from typing import Any

from insights_agent.config import Settings, get_settings
from insights_agent.ratelimit.limiter import RateLimiter, get_rate_limiter
from insights_agent.ratelimit.models import (
    RateLimitStatus,
    get_limits_for_plan,
    get_tier_for_plan,
)

logger = logging.getLogger(__name__)


class RateLimitService:
    """Service for managing rate limits with subscription tier support.

    This service integrates with the marketplace to look up subscription
    tiers and enforce appropriate rate limits.
    """

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        settings: Settings | None = None,
    ):
        """Initialize rate limit service.

        Args:
            rate_limiter: Rate limiter instance.
            settings: Application settings.
        """
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._settings = settings or get_settings()

    async def check_and_enforce(
        self,
        order_id: str,
        plan: str | None = None,
    ) -> tuple[bool, RateLimitStatus]:
        """Check rate limits and return status.

        Args:
            order_id: Order/Entitlement ID.
            plan: Subscription plan name.

        Returns:
            Tuple of (is_allowed, status).
        """
        status = await self._rate_limiter.check_rate_limit(order_id, plan)
        return not status.is_rate_limited, status

    async def record_request(
        self,
        order_id: str,
    ) -> None:
        """Record a request for rate limiting.

        Args:
            order_id: Order/Entitlement ID.
        """
        await self._rate_limiter.increment_request_count(order_id)

    async def record_token_usage(
        self,
        order_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> int:
        """Record token usage.

        Args:
            order_id: Order/Entitlement ID.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Total tokens used today.
        """
        total = input_tokens + output_tokens
        return await self._rate_limiter.add_token_usage(order_id, total)

    async def get_status(
        self,
        order_id: str,
        plan: str | None = None,
    ) -> RateLimitStatus:
        """Get current rate limit status.

        Args:
            order_id: Order/Entitlement ID.
            plan: Subscription plan name.

        Returns:
            Current rate limit status.
        """
        return await self._rate_limiter.check_rate_limit(order_id, plan)

    async def get_tier_info(
        self,
        plan: str | None = None,
    ) -> dict[str, Any]:
        """Get subscription tier information.

        Args:
            plan: Subscription plan name.

        Returns:
            Tier information with limits.
        """
        tier = get_tier_for_plan(plan)
        limits = get_limits_for_plan(plan)

        return {
            "tier": tier.value,
            "plan": plan or "free",
            "limits": {
                "requests_per_minute": limits.requests_per_minute,
                "requests_per_hour": limits.requests_per_hour,
                "tokens_per_day": limits.tokens_per_day,
                "concurrent_requests": limits.concurrent_requests,
            },
        }

    async def reset_limits(
        self,
        order_id: str,
    ) -> None:
        """Reset rate limits for an order (admin function).

        Args:
            order_id: Order/Entitlement ID.
        """
        await self._rate_limiter.reset_limits(order_id)
        logger.info("Rate limits reset for order: %s", order_id)

    async def start_request(
        self,
        order_id: str,
    ) -> int:
        """Start tracking a concurrent request.

        Args:
            order_id: Order/Entitlement ID.

        Returns:
            Current concurrent count.
        """
        return await self._rate_limiter.increment_concurrent(order_id)

    async def end_request(
        self,
        order_id: str,
    ) -> int:
        """End tracking a concurrent request.

        Args:
            order_id: Order/Entitlement ID.

        Returns:
            Current concurrent count.
        """
        return await self._rate_limiter.decrement_concurrent(order_id)

    async def is_token_limited(
        self,
        order_id: str,
        plan: str | None = None,
    ) -> bool:
        """Check if order has exceeded daily token limit.

        Args:
            order_id: Order/Entitlement ID.
            plan: Subscription plan name.

        Returns:
            True if token limit exceeded.
        """
        limits = get_limits_for_plan(plan)
        current = await self._rate_limiter.get_token_usage(order_id)
        return current >= limits.tokens_per_day

    async def get_remaining_tokens(
        self,
        order_id: str,
        plan: str | None = None,
    ) -> int:
        """Get remaining tokens for today.

        Args:
            order_id: Order/Entitlement ID.
            plan: Subscription plan name.

        Returns:
            Remaining tokens.
        """
        limits = get_limits_for_plan(plan)
        current = await self._rate_limiter.get_token_usage(order_id)
        return max(0, limits.tokens_per_day - current)


# Global service instance
_service: RateLimitService | None = None


def get_rate_limit_service() -> RateLimitService:
    """Get the global rate limit service instance.

    Returns:
        RateLimitService instance.
    """
    global _service
    if _service is None:
        _service = RateLimitService()
    return _service
