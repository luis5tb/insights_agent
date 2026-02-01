"""Simplified metering middleware for request tracking."""

import logging
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class MeteringMiddleware(BaseHTTPMiddleware):
    """Simplified middleware for tracking API requests.

    Logs request metrics without per-order tracking.
    Token usage is tracked separately via the UsageTrackingPlugin.
    """

    # Paths to skip metering
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

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and log metrics."""
        path = request.url.path

        # Skip metering for non-API paths
        if path in self.SKIP_PATHS or path.startswith(("/static/", "/favicon")):
            return await call_next(request)

        # Process request
        response = await call_next(request)

        # Log request (token usage is tracked by UsageTrackingPlugin)
        logger.debug(
            f"Request: {request.method} {path} -> {response.status_code}"
        )

        return response
