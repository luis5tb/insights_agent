"""Rate limiting and throttling module.

This module implements rate limiting for the agent:
- Subscription tier-based limits
- Requests per minute/hour
- Tokens per day
- Concurrent request limiting
"""

from insights_agent.ratelimit.limiter import (
    RateLimiter,
    get_rate_limiter,
)
from insights_agent.ratelimit.middleware import (
    RateLimitMiddleware,
    TokenUsageMiddleware,
    get_order_id_from_request,
    get_plan_from_request,
)
from insights_agent.ratelimit.models import (
    PLAN_TO_TIER,
    TIER_LIMITS,
    RateLimitExceeded,
    RateLimits,
    RateLimitStatus,
    SubscriptionTier,
    get_limits_for_plan,
    get_limits_for_tier,
    get_tier_for_plan,
)
from insights_agent.ratelimit.service import (
    RateLimitService,
    get_rate_limit_service,
)

__all__ = [
    # Limiter
    "RateLimiter",
    "get_rate_limiter",
    # Middleware
    "RateLimitMiddleware",
    "TokenUsageMiddleware",
    "get_order_id_from_request",
    "get_plan_from_request",
    # Models
    "PLAN_TO_TIER",
    "TIER_LIMITS",
    "RateLimitExceeded",
    "RateLimits",
    "RateLimitStatus",
    "SubscriptionTier",
    "get_limits_for_plan",
    "get_limits_for_tier",
    "get_tier_for_plan",
    # Service
    "RateLimitService",
    "get_rate_limit_service",
]
