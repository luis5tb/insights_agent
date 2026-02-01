"""Simplified rate limiting module.

This module implements simple global rate limiting for the agent
without per-order tracking.
"""

from insights_agent.ratelimit.middleware import (
    RateLimitMiddleware,
    SimpleRateLimiter,
    get_simple_rate_limiter,
)

__all__ = [
    "RateLimitMiddleware",
    "SimpleRateLimiter",
    "get_simple_rate_limiter",
]
