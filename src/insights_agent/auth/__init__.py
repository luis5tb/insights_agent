"""Authentication and authorization module.

This module implements OAuth 2.0 Authorization Code Grant Flow with Red Hat SSO
as the identity provider, including JWT token validation.
"""

from insights_agent.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_scope,
)
from insights_agent.auth.jwt import JWTValidationError, JWTValidator, get_jwt_validator
from insights_agent.auth.middleware import AuthenticationMiddleware
from insights_agent.auth.models import (
    AuthenticatedUser,
    JWTClaims,
    OAuthError,
    TokenResponse,
    TokenType,
)
from insights_agent.auth.oauth import OAuthClient, get_oauth_client
from insights_agent.auth.router import router as oauth_router

__all__ = [
    # Dependencies
    "CurrentUser",
    "get_current_user",
    "require_scope",
    # JWT
    "JWTValidationError",
    "JWTValidator",
    "get_jwt_validator",
    # Middleware
    "AuthenticationMiddleware",
    # Models
    "AuthenticatedUser",
    "JWTClaims",
    "OAuthError",
    "TokenResponse",
    "TokenType",
    # OAuth
    "OAuthClient",
    "get_oauth_client",
    # Router
    "oauth_router",
]
