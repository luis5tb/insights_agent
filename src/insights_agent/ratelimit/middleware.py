"""Rate limiting middleware for FastAPI."""

import logging
from collections.abc import Callable
from typing import Any, cast

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from insights_agent.ratelimit.limiter import RateLimiter, get_rate_limiter

logger = logging.getLogger(__name__)


def get_order_id_from_request(request: Request) -> str | None:
    """Extract order ID from request.

    The order ID can come from:
    1. Request state (set by auth middleware after token validation)
    2. X-Order-ID header (for internal/trusted calls)

    Args:
        request: FastAPI request.

    Returns:
        Order ID if found, None otherwise.
    """
    # Check request state first (set by auth/marketplace middleware)
    if hasattr(request.state, "order_id"):
        return str(request.state.order_id)

    # Check header for internal calls
    order_id = request.headers.get("X-Order-ID")
    if order_id:
        return order_id

    return None


def get_plan_from_request(request: Request) -> str | None:
    """Extract subscription plan from request.

    Args:
        request: FastAPI request.

    Returns:
        Plan name if found, None otherwise.
    """
    if hasattr(request.state, "plan"):
        return str(request.state.plan)

    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for enforcing rate limits.

    This middleware:
    - Checks rate limits before processing requests
    - Returns 429 Too Many Requests when limits exceeded
    - Includes Retry-After header
    - Tracks concurrent requests
    """

    # Paths to skip rate limiting (health checks, static files, etc.)
    SKIP_PATHS = {
        "/health",
        "/healthz",
        "/ready",
        "/metrics",
        "/.well-known/agent.json",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/oauth/authorize",
        "/oauth/callback",
    }

    # Paths that should be rate limited
    RATE_LIMITED_PATHS = {
        "/a2a",
        "/a2a/stream",
        "/oauth/token",
        "/oauth/userinfo",
    }

    def __init__(self, app: Any, rate_limiter: RateLimiter | None = None):
        """Initialize middleware.

        Args:
            app: FastAPI application.
            rate_limiter: Rate limiter instance.
        """
        super().__init__(app)
        self._rate_limiter = rate_limiter or get_rate_limiter()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request with rate limiting.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response from handler or 429 error.
        """
        path = request.url.path

        # Skip rate limiting for non-billable paths
        if self._should_skip(path):
            return cast(Response, await call_next(request))

        # Get order ID (will be None if not authenticated)
        order_id = get_order_id_from_request(request)

        # If no order ID, allow request but don't track
        # (Authentication will handle unauthorized requests)
        if not order_id:
            return cast(Response, await call_next(request))

        # Get subscription plan
        plan = get_plan_from_request(request)

        try:
            # Check rate limits
            status = await self._rate_limiter.check_rate_limit(order_id, plan)

            if status.is_rate_limited:
                return self._rate_limit_response(status)

            # Increment concurrent counter
            await self._rate_limiter.increment_concurrent(order_id)

            try:
                # Increment request counters
                await self._rate_limiter.increment_request_count(order_id)

                # Process request
                response = await call_next(request)

                # Add rate limit headers
                response = self._add_rate_limit_headers(response, status)

                return response

            finally:
                # Always decrement concurrent counter
                await self._rate_limiter.decrement_concurrent(order_id)

        except Exception as e:
            logger.warning("Rate limiting error (allowing request): %s", e)
            # On error, allow the request through
            return cast(Response, await call_next(request))

    def _should_skip(self, path: str) -> bool:
        """Check if path should skip rate limiting.

        Args:
            path: Request path.

        Returns:
            True if should skip.
        """
        # Exact match for skip paths
        if path in self.SKIP_PATHS:
            return True

        # Prefix match for static paths
        skip_prefixes = ("/static/", "/favicon")
        if path.startswith(skip_prefixes):
            return True

        # Only rate limit specific paths
        for rate_limited_path in self.RATE_LIMITED_PATHS:
            if path == rate_limited_path or path.startswith(f"{rate_limited_path}/"):
                return False

        # Skip rate limiting for unknown paths
        return True

    def _rate_limit_response(self, status: Any) -> JSONResponse:
        """Build rate limit exceeded response.

        Args:
            status: Rate limit status.

        Returns:
            JSON response with 429 status.
        """
        exceeded = self._rate_limiter.build_exceeded_response(status)

        headers = {
            "Retry-After": str(exceeded.retry_after),
            "X-RateLimit-Limit": str(exceeded.limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(exceeded.retry_after),
        }

        return JSONResponse(
            status_code=429,
            content=exceeded.model_dump(),
            headers=headers,
        )

    def _add_rate_limit_headers(
        self,
        response: Response,
        status: Any,
    ) -> Response:
        """Add rate limit headers to response.

        Args:
            response: Outgoing response.
            status: Rate limit status.

        Returns:
            Response with headers.
        """
        # Calculate remaining requests (use minute as primary)
        remaining = max(
            0,
            status.requests_per_minute_limit - status.requests_this_minute - 1,
        )

        response.headers["X-RateLimit-Limit"] = str(status.requests_per_minute_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(60 - (status.requests_this_minute % 60))

        return response


class TokenUsageMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking token usage.

    This middleware is called after request processing to track
    token usage from LLM responses.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and track token usage.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response from handler.
        """
        response = cast(Response, await call_next(request))

        # Check if token usage was recorded in request state
        if hasattr(request.state, "token_usage"):
            order_id = get_order_id_from_request(request)
            if order_id:
                try:
                    rate_limiter = get_rate_limiter()
                    await rate_limiter.add_token_usage(
                        order_id,
                        request.state.token_usage,
                    )
                except Exception as e:
                    logger.warning("Failed to track token usage: %s", e)

        return response
