"""JWT token validation with JWKS support for Red Hat SSO using PyJWT."""

import logging
from datetime import UTC, datetime
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
    PyJWKClientError,
)

from insights_agent.auth.models import AuthenticatedUser, JWTClaims
from insights_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)


class JWTValidationError(Exception):
    """Exception raised when JWT validation fails."""

    pass


class JWTValidator:
    """JWT token validator for Red Hat SSO tokens using PyJWT.

    Uses PyJWKClient for automatic JWKS fetching and caching.
    """

    def __init__(self, settings: Settings | None = None):
        """Initialize JWT validator.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self._settings = settings or get_settings()
        self._jwks_client = PyJWKClient(
            self._settings.red_hat_sso_jwks_uri,
            cache_keys=True,
            lifespan=3600,  # Cache keys for 1 hour
        )

    @property
    def issuer(self) -> str:
        """Get the expected token issuer."""
        return self._settings.red_hat_sso_issuer

    @property
    def client_id(self) -> str:
        """Get the expected client ID (audience)."""
        return self._settings.red_hat_sso_client_id

    async def validate_token(self, token: str) -> AuthenticatedUser:
        """Validate a JWT access token.

        Args:
            token: JWT access token string

        Returns:
            AuthenticatedUser with validated claims

        Raises:
            JWTValidationError: If token validation fails
        """
        # Check if validation should be skipped (development only)
        if self._settings.skip_jwt_validation:
            logger.warning("JWT validation skipped - development mode only")
            return self._create_dev_user(token)

        try:
            # PyJWKClient handles JWKS fetching and caching automatically
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)

            # Decode and validate the token
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                options={
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "require": ["exp", "iat", "iss", "sub"],
                },
            )
        except ExpiredSignatureError as e:
            logger.warning("Token has expired")
            raise JWTValidationError("Token has expired") from e
        except InvalidAudienceError as e:
            logger.warning("Invalid token audience: %s", e)
            raise JWTValidationError(f"Invalid token audience: {e}") from e
        except InvalidIssuerError as e:
            logger.warning("Invalid token issuer: %s", e)
            raise JWTValidationError(f"Invalid token issuer: {e}") from e
        except PyJWKClientError as e:
            logger.error("Failed to fetch signing key: %s", e)
            raise JWTValidationError(f"Failed to fetch signing key: {e}") from e
        except DecodeError as e:
            logger.error("Failed to decode token: %s", e)
            raise JWTValidationError(f"Failed to decode token: {e}") from e
        except InvalidTokenError as e:
            logger.error("Token validation failed: %s", e)
            raise JWTValidationError(f"Token validation failed: {e}") from e

        return self._claims_to_user(claims)

    def _claims_to_user(self, claims: dict[str, Any]) -> AuthenticatedUser:
        """Convert JWT claims to AuthenticatedUser.

        Args:
            claims: Decoded JWT claims

        Returns:
            AuthenticatedUser instance
        """
        jwt_claims = JWTClaims(**claims)

        # Extract client_id from azp (authorized party) or audience
        client_id = jwt_claims.azp
        if not client_id:
            aud = jwt_claims.aud
            client_id = (aud[0] if aud else "") if isinstance(aud, list) else aud

        # Parse scopes
        scopes = []
        if jwt_claims.scope:
            scopes = jwt_claims.scope.split()

        # Build metadata from additional claims
        metadata: dict[str, str] = {}
        # Check for order_id claim (custom claim for marketplace integration)
        if claims.get("order_id"):
            metadata["order_id"] = claims["order_id"]
        # Fallback: use org_id as order_id if available
        elif jwt_claims.org_id:
            metadata["order_id"] = jwt_claims.org_id

        return AuthenticatedUser(
            user_id=jwt_claims.sub,
            client_id=client_id,
            username=jwt_claims.preferred_username,
            email=jwt_claims.email,
            name=jwt_claims.name,
            org_id=jwt_claims.org_id,
            scopes=scopes,
            token_exp=datetime.fromtimestamp(jwt_claims.exp, tz=UTC),
            metadata=metadata,
        )

    def _create_dev_user(self, token: str) -> AuthenticatedUser:
        """Create a development user when validation is skipped.

        Args:
            token: The original token (used to extract claims without validation)

        Returns:
            AuthenticatedUser with development claims
        """
        try:
            # Decode without verification for dev mode
            claims = jwt.decode(token, options={"verify_signature": False})
            return self._claims_to_user(claims)
        except Exception:
            # If we can't decode the token at all, return a default dev user
            return AuthenticatedUser(
                user_id="dev-user",
                client_id="dev-client",
                username="developer",
                email="dev@example.com",
                name="Development User",
                org_id="dev-org",
                scopes=["openid", "profile", "email", "metering:read", "metering:admin"],
                token_exp=datetime.now(UTC).replace(year=2099),
                metadata={"order_id": "dev-order"},
            )

    def get_unverified_header(self, token: str) -> dict[str, Any]:
        """Get the unverified header from a JWT token.

        Args:
            token: JWT token string

        Returns:
            Dictionary containing the JWT header

        Raises:
            JWTValidationError: If the token header cannot be decoded
        """
        try:
            return jwt.get_unverified_header(token)
        except DecodeError as e:
            raise JWTValidationError(f"Failed to decode JWT header: {e}") from e



# Global validator instance (lazily initialized)
_validator: JWTValidator | None = None


def get_jwt_validator() -> JWTValidator:
    """Get the global JWT validator instance.

    Returns:
        JWTValidator instance
    """
    global _validator
    if _validator is None:
        _validator = JWTValidator()
    return _validator
