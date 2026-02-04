"""Keycloak DCR client for creating real OAuth clients in Red Hat SSO."""

import logging
from dataclasses import dataclass

import httpx

from insights_agent.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class KeycloakClientResponse:
    """Response from Keycloak DCR endpoint."""

    client_id: str
    client_secret: str
    client_name: str
    registration_access_token: str | None = None
    registration_client_uri: str | None = None
    redirect_uris: list[str] | None = None


class KeycloakDCRError(Exception):
    """Error from Keycloak DCR operation."""

    def __init__(self, message: str, status_code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class KeycloakDCRClient:
    """Client for Keycloak Dynamic Client Registration.

    Uses Keycloak's DCR endpoint to create real OAuth clients:
    POST /realms/{realm}/clients-registrations/openid-connect

    Requires an Initial Access Token (IAT) from Keycloak admin.
    """

    def __init__(
        self,
        dcr_endpoint: str | None = None,
        initial_access_token: str | None = None,
        client_name_prefix: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the Keycloak DCR client.

        Args:
            dcr_endpoint: Keycloak DCR endpoint URL. Defaults to settings.
            initial_access_token: Initial Access Token for DCR. Defaults to settings.
            client_name_prefix: Prefix for created client names. Defaults to settings.
            http_client: Optional HTTP client for testing.
        """
        settings = get_settings()
        self._dcr_endpoint = dcr_endpoint or settings.keycloak_dcr_endpoint
        self._initial_access_token = initial_access_token or settings.dcr_initial_access_token
        self._client_name_prefix = client_name_prefix or settings.dcr_client_name_prefix
        self._http_client = http_client

    async def create_client(
        self,
        order_id: str,
        redirect_uris: list[str] | None = None,
        grant_types: list[str] | None = None,
    ) -> KeycloakClientResponse:
        """Create a new OAuth client in Keycloak.

        Args:
            order_id: The marketplace order ID (used in client name).
            redirect_uris: OAuth redirect URIs for the client.
            grant_types: OAuth grant types. Defaults to authorization_code, refresh_token.

        Returns:
            KeycloakClientResponse with client credentials.

        Raises:
            KeycloakDCRError: If client creation fails.
        """
        if not self._initial_access_token:
            raise KeycloakDCRError(
                "DCR_INITIAL_ACCESS_TOKEN not configured",
                status_code=500,
            )

        client_name = f"{self._client_name_prefix}{order_id}"

        request_body = {
            "client_name": client_name,
            "redirect_uris": redirect_uris or [],
            "grant_types": grant_types or ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_basic",
            "application_type": "web",
        }

        headers = {
            "Authorization": f"Bearer {self._initial_access_token}",
            "Content-Type": "application/json",
        }

        logger.info(
            "Creating OAuth client in Keycloak: %s",
            client_name,
        )

        try:
            if self._http_client:
                response = await self._http_client.post(
                    self._dcr_endpoint,
                    json=request_body,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self._dcr_endpoint,
                        json=request_body,
                        headers=headers,
                        timeout=30.0,
                    )

            if response.status_code == 201:
                data = response.json()
                logger.info(
                    "Successfully created OAuth client: %s (client_id=%s)",
                    client_name,
                    data.get("client_id"),
                )
                return KeycloakClientResponse(
                    client_id=data["client_id"],
                    client_secret=data["client_secret"],
                    client_name=data.get("client_name", client_name),
                    registration_access_token=data.get("registration_access_token"),
                    registration_client_uri=data.get("registration_client_uri"),
                    redirect_uris=data.get("redirect_uris"),
                )

            # Handle errors
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                error_data = {"error": response.text}

            logger.error(
                "Failed to create OAuth client: status=%d, error=%s",
                response.status_code,
                error_data,
            )

            raise KeycloakDCRError(
                f"Failed to create OAuth client: {error_data.get('error', 'Unknown error')}",
                status_code=response.status_code,
                details=error_data,
            )

        except httpx.RequestError as e:
            logger.exception("HTTP error calling Keycloak DCR: %s", e)
            raise KeycloakDCRError(
                f"HTTP error calling Keycloak DCR: {e}",
                status_code=500,
            ) from e

    async def delete_client(
        self,
        registration_client_uri: str,
        registration_access_token: str,
    ) -> bool:
        """Delete an OAuth client from Keycloak.

        Args:
            registration_client_uri: URI for the client (from creation response).
            registration_access_token: Access token for managing the client.

        Returns:
            True if deleted successfully.

        Raises:
            KeycloakDCRError: If deletion fails.
        """
        headers = {
            "Authorization": f"Bearer {registration_access_token}",
        }

        logger.info("Deleting OAuth client: %s", registration_client_uri)

        try:
            if self._http_client:
                response = await self._http_client.delete(
                    registration_client_uri,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.delete(
                        registration_client_uri,
                        headers=headers,
                        timeout=30.0,
                    )

            if response.status_code == 204:
                logger.info("Successfully deleted OAuth client")
                return True

            logger.error(
                "Failed to delete OAuth client: status=%d",
                response.status_code,
            )
            raise KeycloakDCRError(
                "Failed to delete OAuth client",
                status_code=response.status_code,
            )

        except httpx.RequestError as e:
            logger.exception("HTTP error deleting Keycloak client: %s", e)
            raise KeycloakDCRError(
                f"HTTP error deleting Keycloak client: {e}",
                status_code=500,
            ) from e


# Global client instance
_keycloak_client: KeycloakDCRClient | None = None


def get_keycloak_dcr_client() -> KeycloakDCRClient:
    """Get the global Keycloak DCR client instance.

    Returns:
        KeycloakDCRClient instance.
    """
    global _keycloak_client
    if _keycloak_client is None:
        _keycloak_client = KeycloakDCRClient()
    return _keycloak_client
