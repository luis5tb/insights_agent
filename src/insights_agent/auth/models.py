"""Pydantic models for authentication and authorization."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TokenType(str, Enum):
    """Token type enumeration."""

    BEARER = "Bearer"


class TokenResponse(BaseModel):
    """OAuth 2.0 token response."""

    access_token: str = Field(..., description="The access token")
    token_type: TokenType = Field(default=TokenType.BEARER, description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    refresh_token: str | None = Field(default=None, description="Refresh token")
    scope: str | None = Field(default=None, description="Token scope")


class TokenRequest(BaseModel):
    """OAuth 2.0 token request."""

    grant_type: str = Field(..., description="Grant type")
    code: str | None = Field(default=None, description="Authorization code")
    redirect_uri: str | None = Field(default=None, description="Redirect URI")
    refresh_token: str | None = Field(default=None, description="Refresh token")
    client_id: str | None = Field(default=None, description="Client ID")
    client_secret: str | None = Field(default=None, description="Client secret")


class AuthorizationRequest(BaseModel):
    """OAuth 2.0 authorization request parameters."""

    response_type: str = Field(default="code", description="Response type")
    client_id: str = Field(..., description="Client ID")
    redirect_uri: str = Field(..., description="Redirect URI")
    scope: str = Field(default="openid", description="Requested scope")
    state: str | None = Field(default=None, description="State parameter for CSRF protection")


class AuthorizationCallback(BaseModel):
    """OAuth 2.0 authorization callback parameters."""

    code: str = Field(..., description="Authorization code")
    state: str | None = Field(default=None, description="State parameter")


class JWTClaims(BaseModel):
    """JWT token claims."""

    iss: str = Field(..., description="Issuer")
    sub: str = Field(..., description="Subject (user ID)")
    aud: str | list[str] = Field(..., description="Audience")
    exp: int = Field(..., description="Expiration time (Unix timestamp)")
    iat: int = Field(..., description="Issued at time (Unix timestamp)")
    jti: str | None = Field(default=None, description="JWT ID")
    azp: str | None = Field(default=None, description="Authorized party (client_id)")
    scope: str | None = Field(default=None, description="Token scope")
    preferred_username: str | None = Field(default=None, description="Preferred username")
    email: str | None = Field(default=None, description="Email address")
    name: str | None = Field(default=None, description="Full name")
    org_id: str | None = Field(default=None, description="Organization ID")


class AuthenticatedUser(BaseModel):
    """Authenticated user information extracted from JWT."""

    user_id: str = Field(..., description="User ID (sub claim)")
    client_id: str = Field(..., description="Client ID (azp or aud claim)")
    username: str | None = Field(default=None, description="Username")
    email: str | None = Field(default=None, description="Email")
    name: str | None = Field(default=None, description="Full name")
    org_id: str | None = Field(default=None, description="Organization ID")
    scopes: list[str] = Field(default_factory=list, description="Granted scopes")
    token_exp: datetime = Field(..., description="Token expiration time")
    # Metadata for additional claims (order_id, etc.)
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Additional metadata from token claims",
    )
    # Raw access token for forwarding to downstream services (e.g., MCP)
    access_token: str | None = Field(
        default=None,
        description="Raw access token for forwarding to downstream services",
        exclude=True,  # Exclude from serialization for security
    )


class OAuthError(BaseModel):
    """OAuth 2.0 error response."""

    error: str = Field(..., description="Error code")
    error_description: str | None = Field(default=None, description="Error description")
    error_uri: str | None = Field(default=None, description="Error URI")


class JWKS(BaseModel):
    """JSON Web Key Set."""

    keys: list[dict[str, str]] = Field(..., description="List of JWK keys")
