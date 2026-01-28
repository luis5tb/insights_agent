"""Rate limiting data models and subscription tiers."""

from enum import Enum
from typing import NamedTuple

from pydantic import BaseModel, Field


class SubscriptionTier(str, Enum):
    """Subscription tier levels."""

    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class RateLimits(NamedTuple):
    """Rate limits for a subscription tier."""

    requests_per_minute: int
    requests_per_hour: int
    tokens_per_day: int
    concurrent_requests: int


# Default rate limits per subscription tier
TIER_LIMITS: dict[SubscriptionTier, RateLimits] = {
    SubscriptionTier.FREE: RateLimits(
        requests_per_minute=10,
        requests_per_hour=100,
        tokens_per_day=10_000,
        concurrent_requests=2,
    ),
    SubscriptionTier.BASIC: RateLimits(
        requests_per_minute=30,
        requests_per_hour=500,
        tokens_per_day=50_000,
        concurrent_requests=5,
    ),
    SubscriptionTier.PROFESSIONAL: RateLimits(
        requests_per_minute=60,
        requests_per_hour=1_000,
        tokens_per_day=100_000,
        concurrent_requests=10,
    ),
    SubscriptionTier.ENTERPRISE: RateLimits(
        requests_per_minute=300,
        requests_per_hour=10_000,
        tokens_per_day=1_000_000,
        concurrent_requests=50,
    ),
}

# Plan name to tier mapping
PLAN_TO_TIER: dict[str, SubscriptionTier] = {
    # Free tier
    "free": SubscriptionTier.FREE,
    "trial": SubscriptionTier.FREE,
    # Basic tier
    "basic": SubscriptionTier.BASIC,
    "starter": SubscriptionTier.BASIC,
    # Professional tier
    "professional": SubscriptionTier.PROFESSIONAL,
    "pro": SubscriptionTier.PROFESSIONAL,
    "standard": SubscriptionTier.PROFESSIONAL,
    # Enterprise tier
    "enterprise": SubscriptionTier.ENTERPRISE,
    "premium": SubscriptionTier.ENTERPRISE,
    "unlimited": SubscriptionTier.ENTERPRISE,
}


def get_tier_for_plan(plan: str | None) -> SubscriptionTier:
    """Get subscription tier for a plan name.

    Args:
        plan: Plan name from marketplace entitlement.

    Returns:
        Subscription tier.
    """
    if not plan:
        return SubscriptionTier.FREE

    plan_lower = plan.lower()
    return PLAN_TO_TIER.get(plan_lower, SubscriptionTier.FREE)


def get_limits_for_tier(tier: SubscriptionTier) -> RateLimits:
    """Get rate limits for a subscription tier.

    Args:
        tier: Subscription tier.

    Returns:
        Rate limits for the tier.
    """
    return TIER_LIMITS.get(tier, TIER_LIMITS[SubscriptionTier.FREE])


def get_limits_for_plan(plan: str | None) -> RateLimits:
    """Get rate limits for a plan name.

    Args:
        plan: Plan name from marketplace entitlement.

    Returns:
        Rate limits for the plan.
    """
    tier = get_tier_for_plan(plan)
    return get_limits_for_tier(tier)


class RateLimitStatus(BaseModel):
    """Current rate limit status for a client."""

    order_id: str = Field(..., description="Order/Entitlement ID")
    tier: SubscriptionTier = Field(..., description="Subscription tier")

    # Current usage
    requests_this_minute: int = Field(0, description="Requests in current minute")
    requests_this_hour: int = Field(0, description="Requests in current hour")
    tokens_today: int = Field(0, description="Tokens used today")
    concurrent_requests: int = Field(0, description="Current concurrent requests")

    # Limits
    requests_per_minute_limit: int = Field(..., description="Requests per minute limit")
    requests_per_hour_limit: int = Field(..., description="Requests per hour limit")
    tokens_per_day_limit: int = Field(..., description="Tokens per day limit")
    concurrent_requests_limit: int = Field(..., description="Concurrent requests limit")

    # Status
    is_rate_limited: bool = Field(False, description="Whether currently rate limited")
    retry_after_seconds: int | None = Field(
        None, description="Seconds until rate limit resets"
    )
    limit_type: str | None = Field(
        None, description="Type of limit exceeded (minute, hour, day, concurrent)"
    )


class RateLimitExceeded(BaseModel):
    """Rate limit exceeded response."""

    error: str = Field(
        default="rate_limit_exceeded",
        description="Error code",
    )
    message: str = Field(..., description="Human-readable error message")
    limit_type: str = Field(..., description="Type of limit exceeded")
    limit: int = Field(..., description="The limit value")
    current: int = Field(..., description="Current usage value")
    retry_after: int = Field(..., description="Seconds until limit resets")
    tier: SubscriptionTier = Field(..., description="Current subscription tier")
