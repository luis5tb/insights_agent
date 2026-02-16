"""Authentication and authorization module.

This module implements OAuth 2.0 with Red Hat SSO as the identity provider.
Bearer tokens are validated via Keycloak token introspection (RFC 7662) and
checked for the required ``agent:insights`` scope.
"""

from lightspeed_agent.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_scope,
)
from lightspeed_agent.auth.introspection import (
    InsufficientScopeError,
    TokenIntrospector,
    TokenValidationError,
    get_token_introspector,
)
from lightspeed_agent.auth.middleware import AuthenticationMiddleware
from lightspeed_agent.auth.models import (
    AuthenticatedUser,
    JWTClaims,
    OAuthError,
    TokenResponse,
    TokenType,
)
from lightspeed_agent.auth.oauth import OAuthClient, get_oauth_client
from lightspeed_agent.auth.router import router as oauth_router

__all__ = [
    # Dependencies
    "CurrentUser",
    "get_current_user",
    "require_scope",
    # Introspection
    "TokenIntrospector",
    "TokenValidationError",
    "InsufficientScopeError",
    "get_token_introspector",
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
