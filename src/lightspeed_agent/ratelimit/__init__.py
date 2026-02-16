"""Simplified rate limiting module.

This module implements simple global rate limiting for the agent
without per-order tracking.
"""

from lightspeed_agent.ratelimit.middleware import RateLimitMiddleware

__all__ = [
    "RateLimitMiddleware",
]
