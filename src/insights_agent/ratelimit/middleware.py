"""Simplified rate limiting middleware with global limits."""

import time
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from insights_agent.config import get_settings



class SimpleRateLimiter:
    """Simple in-memory rate limiter with sliding window."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        self._requests_per_minute = requests_per_minute
        self._requests_per_hour = requests_per_hour
        self._minute_window: list[float] = []
        self._hour_window: list[float] = []

    def is_allowed(self) -> tuple[bool, dict]:
        """Check if request is allowed under rate limits.

        Returns:
            Tuple of (is_allowed, status_dict with limit info).
        """
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        # Clean old entries
        self._minute_window = [t for t in self._minute_window if t > minute_ago]
        self._hour_window = [t for t in self._hour_window if t > hour_ago]

        minute_count = len(self._minute_window)
        hour_count = len(self._hour_window)

        status = {
            "requests_this_minute": minute_count,
            "requests_this_hour": hour_count,
            "limit_per_minute": self._requests_per_minute,
            "limit_per_hour": self._requests_per_hour,
        }

        # Check limits
        if minute_count >= self._requests_per_minute:
            return False, {**status, "exceeded": "per_minute", "retry_after": 60}
        if hour_count >= self._requests_per_hour:
            return False, {**status, "exceeded": "per_hour", "retry_after": 3600}

        # Record request
        self._minute_window.append(now)
        self._hour_window.append(now)

        return True, status


# Global rate limiter instance
_rate_limiter: SimpleRateLimiter | None = None


def get_simple_rate_limiter() -> SimpleRateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = SimpleRateLimiter(
            requests_per_minute=settings.rate_limit_requests_per_minute,
            requests_per_hour=settings.rate_limit_requests_per_hour,
        )
    return _rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simplified middleware for global rate limiting.

    Applies rate limits to A2A endpoints without per-order tracking.
    """

    # Paths to skip rate limiting
    SKIP_PATHS = {
        "/health",
        "/healthz",
        "/ready",
        "/metrics",
        "/.well-known/agent.json",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    # Paths that should be rate limited (A2A JSON-RPC endpoint)
    RATE_LIMITED_PATHS = {"/"}

    def __init__(self, app: Any):
        super().__init__(app)
        self._limiter = get_simple_rate_limiter()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request with rate limiting."""
        path = request.url.path

        # Skip rate limiting for non-API paths
        if self._should_skip(path):
            return await call_next(request)

        # Check rate limit
        allowed, status = self._limiter.is_allowed()

        if not allowed:
            return self._rate_limit_response(status)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(status["limit_per_minute"])
        response.headers["X-RateLimit-Remaining"] = str(
            status["limit_per_minute"] - status["requests_this_minute"]
        )

        return response

    def _should_skip(self, path: str) -> bool:
        """Check if path should skip rate limiting."""
        if path in self.SKIP_PATHS:
            return True

        # Only rate limit specific paths
        for rate_limited_path in self.RATE_LIMITED_PATHS:
            if path == rate_limited_path or path.startswith(f"{rate_limited_path}/"):
                return False

        return True

    def _rate_limit_response(self, status: dict) -> JSONResponse:
        """Build rate limit exceeded response."""
        retry_after = status.get("retry_after", 60)

        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded ({status.get('exceeded', 'unknown')})",
                "retry_after": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(status["limit_per_minute"]),
                "X-RateLimit-Remaining": "0",
            },
        )
