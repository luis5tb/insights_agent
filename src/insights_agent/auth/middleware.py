"""Authentication middleware for A2A endpoints."""

import logging
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from insights_agent.auth.jwt import JWTValidationError, get_jwt_validator
from insights_agent.config import get_settings

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce Red Hat SSO authentication on A2A endpoints.

    This middleware validates Bearer tokens on protected endpoints using
    the Red Hat SSO JWT validator. The AgentCard endpoint is left public
    for agent discovery.
    """

    # Paths that require authentication (POST only)
    PROTECTED_PATHS = {"/"}

    # Paths that are always public (no auth required)
    PUBLIC_PATHS = {
        "/health",
        "/healthz",
        "/ready",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/.well-known/agent.json",
        "/.well-known/agent-card.json",
        "/oauth/authorize",
        "/oauth/callback",
        "/oauth/token",
        "/oauth/register",  # DCR endpoint uses software_statement JWT
        "/marketplace/pubsub",  # Pub/Sub uses Google-signed tokens
    }

    # Path prefixes that are public
    PUBLIC_PREFIXES = (
        "/oauth/",
        "/marketplace/",
    )

    def __init__(self, app: Any):
        super().__init__(app)
        self._settings = get_settings()

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        """Process request with authentication check."""
        path = request.url.path
        method = request.method

        # Skip authentication for public paths
        if self._is_public(path, method):
            return await call_next(request)

        # Skip authentication in development mode
        if self._settings.skip_jwt_validation:
            logger.debug("Skipping authentication (development mode)")
            return await call_next(request)

        # Check for Bearer token
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return self._unauthorized_response("Missing Authorization header")

        if not auth_header.startswith("Bearer "):
            return self._unauthorized_response("Invalid Authorization header format")

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Validate token
        try:
            jwt_validator = get_jwt_validator()
            user = await jwt_validator.validate_token(token)
            # Store user in request state for access in handlers
            request.state.user = user
            request.state.access_token = token
            logger.debug("Authenticated user: %s", user.sub)
        except JWTValidationError as e:
            logger.warning("JWT validation failed: %s", e)
            return self._unauthorized_response(str(e))

        return await call_next(request)

    def _is_public(self, path: str, method: str) -> bool:
        """Check if path/method combination is public."""
        # Explicit public paths
        if path in self.PUBLIC_PATHS:
            return True

        # Public prefixes
        if path.startswith(self.PUBLIC_PREFIXES):
            return True

        # GET requests to root are public (for compatibility)
        if path == "/" and method == "GET":
            return True

        # Only POST to protected paths requires auth
        if path in self.PROTECTED_PATHS and method == "POST":
            return False

        # Everything else is public by default
        return True

    def _unauthorized_response(self, detail: str) -> JSONResponse:
        """Build 401 Unauthorized response."""
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32001,
                    "message": "Unauthorized",
                    "data": {"detail": detail},
                },
                "id": None,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
