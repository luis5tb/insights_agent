"""OAuth 2.0 Authorization Code Grant Flow implementation."""

import logging
import secrets
from urllib.parse import urlencode

import httpx

from lightspeed_agent.auth.models import OAuthError, TokenResponse
from lightspeed_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)


class OAuthClient:
    """OAuth 2.0 client for Red Hat SSO."""

    def __init__(self, settings: Settings | None = None):
        """Initialize OAuth client.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self._settings = settings or get_settings()

    @property
    def issuer(self) -> str:
        """Get the OAuth issuer URL."""
        return self._settings.red_hat_sso_issuer

    @property
    def client_id(self) -> str:
        """Get the OAuth client ID."""
        return self._settings.red_hat_sso_client_id

    @property
    def client_secret(self) -> str:
        """Get the OAuth client secret."""
        return self._settings.red_hat_sso_client_secret

    @property
    def redirect_uri(self) -> str:
        """Get the OAuth redirect URI."""
        return self._settings.red_hat_sso_redirect_uri

    @property
    def authorization_endpoint(self) -> str:
        """Get the authorization endpoint URL."""
        return f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def token_endpoint(self) -> str:
        """Get the token endpoint URL."""
        return f"{self.issuer}/protocol/openid-connect/token"

    @property
    def userinfo_endpoint(self) -> str:
        """Get the userinfo endpoint URL."""
        return f"{self.issuer}/protocol/openid-connect/userinfo"

    def generate_state(self) -> str:
        """Generate a cryptographically secure state parameter.

        Returns:
            Random URL-safe string for state parameter
        """
        return secrets.token_urlsafe(32)

    def build_authorization_url(
        self,
        state: str,
        scope: str = "openid profile email",
        redirect_uri: str | None = None,
    ) -> str:
        """Build the authorization URL for redirecting to Red Hat SSO.

        Args:
            state: State parameter for CSRF protection
            scope: OAuth scopes to request
            redirect_uri: Override redirect URI (uses configured default if None)

        Returns:
            Full authorization URL
        """
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "scope": scope,
            "state": state,
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str | None = None,
    ) -> TokenResponse | OAuthError:
        """Exchange an authorization code for tokens.

        Args:
            code: Authorization code from callback
            redirect_uri: Redirect URI used in authorization request

        Returns:
            TokenResponse on success, OAuthError on failure
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        return await self._token_request(data)

    async def refresh_token(self, refresh_token: str) -> TokenResponse | OAuthError:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: Refresh token from previous token response

        Returns:
            TokenResponse on success, OAuthError on failure
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        return await self._token_request(data)

    async def _token_request(
        self,
        data: dict[str, str],
    ) -> TokenResponse | OAuthError:
        """Make a token request to the token endpoint.

        Args:
            data: Form data for token request

        Returns:
            TokenResponse on success, OAuthError on failure
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30.0,
                )

                response_data = response.json()

                if response.status_code == 200:
                    return TokenResponse(**response_data)
                else:
                    logger.error(
                        "Token request failed: %s %s",
                        response.status_code,
                        response_data,
                    )
                    return OAuthError(
                        error=response_data.get("error", "unknown_error"),
                        error_description=response_data.get("error_description"),
                    )
        except httpx.HTTPError as e:
            logger.error("HTTP error during token request: %s", e)
            return OAuthError(
                error="server_error",
                error_description=f"Failed to communicate with token endpoint: {e}",
            )
        except Exception as e:
            logger.error("Unexpected error during token request: %s", e)
            return OAuthError(
                error="server_error",
                error_description=f"Unexpected error: {e}",
            )

    async def get_userinfo(self, access_token: str) -> dict[str, str] | OAuthError:
        """Fetch user information from the userinfo endpoint.

        Args:
            access_token: Valid access token

        Returns:
            User info dictionary on success, OAuthError on failure
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    result: dict[str, str] = response.json()
                    return result
                else:
                    response_data = response.json()
                    return OAuthError(
                        error=response_data.get("error", "invalid_token"),
                        error_description=response_data.get("error_description"),
                    )
        except httpx.HTTPError as e:
            logger.error("HTTP error during userinfo request: %s", e)
            return OAuthError(
                error="server_error",
                error_description=f"Failed to fetch user info: {e}",
            )


# Global OAuth client instance (lazily initialized)
_oauth_client: OAuthClient | None = None


def get_oauth_client() -> OAuthClient:
    """Get the global OAuth client instance.

    Returns:
        OAuthClient instance
    """
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = OAuthClient()
    return _oauth_client
