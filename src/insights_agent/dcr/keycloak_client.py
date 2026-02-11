"""Keycloak DCR client for creating real OAuth clients in Red Hat SSO."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from insights_agent.config import get_settings

if TYPE_CHECKING:
    from insights_agent.config.settings import Settings

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

        settings = get_settings()

        request_body = {
            "client_name": client_name,
            "redirect_uris": redirect_uris or [],
            "grant_types": grant_types or ["authorization_code", "refresh_token", "client_credentials"],
            "token_endpoint_auth_method": "client_secret_basic",
            "application_type": "web",
            "scope": f"openid {settings.agent_required_scope}",
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
                oauth_client_id = data["client_id"]
                logger.info(
                    "Successfully created OAuth client: %s (client_id=%s)",
                    client_name,
                    oauth_client_id,
                )

                # Keycloak's OIDC DCR endpoint ignores the grant_types
                # and scope fields: serviceAccountsEnabled is not set, and
                # the requested scopes are not assigned as client scopes.
                # Fix both via the Admin API.
                await self._post_dcr_setup(oauth_client_id, settings)

                return KeycloakClientResponse(
                    client_id=oauth_client_id,
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

    async def _post_dcr_setup(
        self,
        oauth_client_id: str,
        settings: "Settings",
    ) -> None:
        """Fix up a DCR-created client via the Keycloak Admin API.

        Keycloak's OIDC DCR endpoint ignores several fields:

        * ``grant_types`` containing ``client_credentials`` does **not** set
          ``serviceAccountsEnabled``.
        * The ``scope`` field is stored as metadata but the corresponding
          client scopes are **not** assigned to the client.

        This method uses the agent's own credentials to call the Admin API
        and fix both.  Requires the ``manage-clients`` realm role.
        Failures are logged but do not block the DCR response.
        """
        admin_base = settings.keycloak_admin_api_base
        token_url = settings.keycloak_token_endpoint

        try:
            async with httpx.AsyncClient() as http:
                # 1. Get a token using the agent's own credentials
                token_resp = await http.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.red_hat_sso_client_id,
                        "client_secret": settings.red_hat_sso_client_secret,
                    },
                    timeout=30.0,
                )
                if token_resp.status_code != 200:
                    logger.warning(
                        "Post-DCR setup failed for %s: "
                        "could not get admin token (status %d)",
                        oauth_client_id,
                        token_resp.status_code,
                    )
                    return

                admin_token = token_resp.json()["access_token"]
                admin_headers = {"Authorization": f"Bearer {admin_token}"}

                # 2. Look up the client by OAuth client_id
                lookup_resp = await http.get(
                    f"{admin_base}/clients",
                    params={"clientId": oauth_client_id},
                    headers=admin_headers,
                    timeout=30.0,
                )
                clients = lookup_resp.json() if lookup_resp.status_code == 200 else []
                if not clients:
                    logger.warning(
                        "Post-DCR setup failed: client %s not found in Admin API",
                        oauth_client_id,
                    )
                    return

                kc_client = clients[0]
                kc_uuid = kc_client["id"]

                # 3. Enable service accounts
                kc_client["serviceAccountsEnabled"] = True
                update_resp = await http.put(
                    f"{admin_base}/clients/{kc_uuid}",
                    json=kc_client,
                    headers={**admin_headers, "Content-Type": "application/json"},
                    timeout=30.0,
                )
                if update_resp.status_code == 204:
                    logger.info(
                        "Enabled service accounts on client %s",
                        oauth_client_id,
                    )
                else:
                    logger.warning(
                        "Failed to enable service accounts on %s: %d %s",
                        oauth_client_id,
                        update_resp.status_code,
                        update_resp.text,
                    )

                # 4. Assign the required scope as an optional client scope
                await self._assign_scope(
                    http, admin_base, admin_headers,
                    kc_uuid, oauth_client_id,
                    settings.agent_required_scope,
                )
        except Exception:
            logger.exception(
                "Error in post-DCR setup for client %s",
                oauth_client_id,
            )

    async def _assign_scope(
        self,
        http: httpx.AsyncClient,
        admin_base: str,
        admin_headers: dict[str, str],
        kc_client_uuid: str,
        oauth_client_id: str,
        scope_name: str,
    ) -> None:
        """Assign a client scope to a DCR-created client."""
        # Find the scope UUID by name
        scopes_resp = await http.get(
            f"{admin_base}/client-scopes",
            headers=admin_headers,
            timeout=30.0,
        )
        if scopes_resp.status_code != 200:
            logger.warning(
                "Could not list client scopes to assign %s: %d",
                scope_name,
                scopes_resp.status_code,
            )
            return

        scope_uuid = None
        for scope in scopes_resp.json():
            if scope.get("name") == scope_name:
                scope_uuid = scope["id"]
                break

        if not scope_uuid:
            logger.warning(
                "Client scope %s not found in realm — "
                "cannot assign to client %s",
                scope_name,
                oauth_client_id,
            )
            return

        # Assign as optional scope (client must explicitly request it)
        assign_resp = await http.put(
            f"{admin_base}/clients/{kc_client_uuid}"
            f"/optional-client-scopes/{scope_uuid}",
            headers=admin_headers,
            timeout=30.0,
        )
        if assign_resp.status_code == 204:
            logger.info(
                "Assigned scope %s to client %s",
                scope_name,
                oauth_client_id,
            )
        else:
            logger.warning(
                "Failed to assign scope %s to client %s: %d %s",
                scope_name,
                oauth_client_id,
                assign_resp.status_code,
                assign_resp.text,
            )

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
