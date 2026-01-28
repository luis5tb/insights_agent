"""Metering middleware for automatic usage tracking."""

import logging
from typing import Any, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from insights_agent.metering.service import get_metering_service

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
    # Check request state first (set by auth middleware)
    if hasattr(request.state, "order_id"):
        return request.state.order_id

    # Check header for internal calls
    order_id = request.headers.get("X-Order-ID")
    if order_id:
        return order_id

    return None


def get_client_id_from_request(request: Request) -> str | None:
    """Extract client ID from request.

    Args:
        request: FastAPI request.

    Returns:
        Client ID if found, None otherwise.
    """
    if hasattr(request.state, "client_id"):
        return request.state.client_id

    return None


def get_context_id_from_request(request: Request) -> str | None:
    """Extract context ID from request.

    Args:
        request: FastAPI request.

    Returns:
        Context ID if found, None otherwise.
    """
    if hasattr(request.state, "context_id"):
        return request.state.context_id

    # Check header
    context_id = request.headers.get("X-Context-ID")
    if context_id:
        return context_id

    return None


class MeteringMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking API usage.

    This middleware:
    - Extracts order ID from authenticated requests
    - Tracks API calls for metering
    - Records errors for monitoring
    """

    # Paths to skip metering (health checks, static files, etc.)
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

    # Paths that are billable A2A endpoints
    A2A_PATHS = {
        "/a2a",
        "/a2a/stream",
    }

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and track usage.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response from handler.
        """
        path = request.url.path

        # Skip metering for non-billable paths
        if self._should_skip(path):
            return await call_next(request)

        # Get order ID (will be None if not authenticated)
        order_id = get_order_id_from_request(request)

        # Process request
        response = await call_next(request)

        # Only track if we have an order ID
        if order_id:
            await self._track_request(request, response, order_id)

        return response

    def _should_skip(self, path: str) -> bool:
        """Check if path should skip metering.

        Args:
            path: Request path.

        Returns:
            True if should skip.
        """
        # Exact match
        if path in self.SKIP_PATHS:
            return True

        # Prefix match for static paths
        skip_prefixes = ("/static/", "/favicon")
        if path.startswith(skip_prefixes):
            return True

        return False

    async def _track_request(
        self,
        request: Request,
        response: Response,
        order_id: str,
    ) -> None:
        """Track request usage.

        Args:
            request: Incoming request.
            response: Outgoing response.
            order_id: Order ID for billing.
        """
        try:
            metering = get_metering_service()
            client_id = get_client_id_from_request(request)
            context_id = get_context_id_from_request(request)
            path = request.url.path

            # Check if this is an A2A endpoint
            is_streaming = path == "/a2a/stream"
            is_a2a = path in self.A2A_PATHS

            if is_a2a:
                # Track as API call
                await metering.track_api_call(
                    order_id=order_id,
                    client_id=client_id,
                    context_id=context_id,
                    streaming=is_streaming,
                    metadata={
                        "path": path,
                        "method": request.method,
                    },
                )

            # Track errors
            if response.status_code >= 400:
                error_type = self._classify_error(response.status_code)
                await metering.track_error(
                    order_id=order_id,
                    error_type=error_type,
                    client_id=client_id,
                    context_id=context_id,
                )

            # Track rate limiting
            if response.status_code == 429:
                await metering.track_rate_limited(
                    order_id=order_id,
                    client_id=client_id,
                )

        except Exception as e:
            # Don't fail request due to metering errors
            logger.warning("Failed to track usage: %s", e)

    def _classify_error(self, status_code: int) -> str:
        """Classify error by status code.

        Args:
            status_code: HTTP status code.

        Returns:
            Error type string.
        """
        if status_code == 400:
            return "bad_request"
        elif status_code == 401:
            return "unauthorized"
        elif status_code == 403:
            return "forbidden"
        elif status_code == 404:
            return "not_found"
        elif status_code == 429:
            return "rate_limited"
        elif 400 <= status_code < 500:
            return "client_error"
        elif 500 <= status_code < 600:
            return "server_error"
        else:
            return "unknown"
