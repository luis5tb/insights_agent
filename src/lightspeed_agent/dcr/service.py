"""DCR service for handling Dynamic Client Registration requests."""

import logging

from cryptography.fernet import Fernet, InvalidToken

from lightspeed_agent.config import get_settings
from lightspeed_agent.dcr.google_jwt import GoogleJWTValidator, get_google_jwt_validator
from lightspeed_agent.dcr.keycloak_client import (
    KeycloakDCRClient,
    KeycloakDCRError,
    get_keycloak_dcr_client,
)
from lightspeed_agent.dcr.models import (
    DCRError,
    DCRErrorCode,
    DCRRequest,
    DCRResponse,
    GoogleJWTClaims,
    RegisteredClient,
)
from lightspeed_agent.dcr.repository import DCRClientRepository, get_dcr_client_repository
from lightspeed_agent.marketplace.service import ProcurementService, get_procurement_service

logger = logging.getLogger(__name__)


class DCRService:
    """Service for handling Dynamic Client Registration.

    This service:
    - Validates software_statement JWTs from Google
    - Cross-references with Marketplace Procurement data
    - Creates OAuth client credentials (real DCR or pre-seeded)
    - Returns RFC 7591 compliant responses

    Modes:
    - DCR_ENABLED=true: Creates real OAuth clients in Red Hat SSO (Keycloak)
    - DCR_ENABLED=false: Returns pre-seeded credentials from the database
      (seeded via seed_dcr_clients.py). Returns an error if no credentials
      are registered for the order.
    """

    def __init__(
        self,
        jwt_validator: GoogleJWTValidator | None = None,
        procurement_service: ProcurementService | None = None,
        keycloak_client: KeycloakDCRClient | None = None,
        client_repository: DCRClientRepository | None = None,
    ) -> None:
        """Initialize the DCR service.

        Args:
            jwt_validator: Google JWT validator.
            procurement_service: Procurement service for validation.
            keycloak_client: Keycloak DCR client for real DCR.
            client_repository: Repository for storing client mappings.
        """
        self._jwt_validator = jwt_validator or get_google_jwt_validator()
        self._procurement_service = procurement_service or get_procurement_service()
        self._keycloak_client = keycloak_client
        self._client_repository = client_repository or get_dcr_client_repository()
        self._settings = get_settings()

        # Fernet cipher for encrypting client secrets
        self._fernet: Fernet | None = None
        if self._settings.dcr_encryption_key:
            try:
                self._fernet = Fernet(self._settings.dcr_encryption_key.encode())
            except Exception as e:
                logger.error("Invalid DCR encryption key: %s", e)

    def _get_keycloak_client(self) -> KeycloakDCRClient:
        """Get the Keycloak DCR client (lazy initialization)."""
        if self._keycloak_client is None:
            self._keycloak_client = get_keycloak_dcr_client()
        return self._keycloak_client

    def _encrypt_secret(self, secret: str) -> str:
        """Encrypt a client secret for storage.

        Args:
            secret: The plaintext client secret.

        Returns:
            Encrypted secret as base64 string.
        """
        if not self._fernet:
            logger.warning("DCR_ENCRYPTION_KEY not set, using ephemeral key")
            self._fernet = Fernet(Fernet.generate_key())
        return self._fernet.encrypt(secret.encode()).decode()

    def _decrypt_secret(self, encrypted_secret: str) -> str | None:
        """Decrypt a stored client secret.

        Args:
            encrypted_secret: The encrypted secret.

        Returns:
            Decrypted secret or None if decryption fails.
        """
        if not self._fernet:
            logger.error("Cannot decrypt: no encryption key available")
            return None
        try:
            return self._fernet.decrypt(encrypted_secret.encode()).decode()
        except InvalidToken:
            logger.error("Failed to decrypt client secret: invalid token")
            return None

    async def register_client(
        self,
        request: DCRRequest,
    ) -> DCRResponse | DCRError:
        """Process a Dynamic Client Registration request.

        Args:
            request: The DCR request containing software_statement.

        Returns:
            DCRResponse on success, DCRError on failure.
        """
        logger.info("Processing DCR request (dcr_enabled=%s)", self._settings.dcr_enabled)

        # Step 1: Validate the software_statement JWT
        validation_result = await self._jwt_validator.validate_software_statement(
            request.software_statement
        )

        if isinstance(validation_result, DCRError):
            return validation_result

        claims: GoogleJWTClaims = validation_result

        # Step 2: Validate the Procurement Account ID
        if not await self._validate_account(claims.account_id):
            logger.warning("Invalid Procurement Account ID: %s", claims.account_id)
            return DCRError(
                error=DCRErrorCode.UNAPPROVED_SOFTWARE_STATEMENT,
                error_description=f"Invalid Procurement Account ID: {claims.account_id}",
            )

        # Step 3: Validate the Order ID
        if not await self._validate_order(claims.order_id):
            logger.warning("Invalid Order ID: %s", claims.order_id)
            return DCRError(
                error=DCRErrorCode.UNAPPROVED_SOFTWARE_STATEMENT,
                error_description=f"Invalid Order ID: {claims.order_id}",
            )

        # Step 4: Check if client already exists for this order
        existing_client = await self._client_repository.get_by_order_id(claims.order_id)
        if existing_client:
            logger.info(
                "Returning existing credentials for order: %s (client_id=%s)",
                claims.order_id,
                existing_client.client_id,
            )
            return await self._return_existing_credentials(existing_client)

        # Step 5: Create new OAuth client credentials
        if self._settings.dcr_enabled:
            return await self._create_real_client(claims)

        # DCR disabled: no pre-seeded credentials found for this order.
        # Credentials must be seeded in advance using seed_dcr_clients.py.
        logger.warning(
            "DCR disabled and no pre-seeded credentials for order: %s",
            claims.order_id,
        )
        return DCRError(
            error=DCRErrorCode.SERVER_ERROR,
            error_description=(
                f"No client credentials registered for order: {claims.order_id}. "
                "Use seed_dcr_clients.py to pre-register credentials."
            ),
        )

    async def _validate_account(self, account_id: str) -> bool:
        """Validate that the Procurement Account ID is valid."""
        if self._settings.skip_jwt_validation:
            logger.warning("Skipping account validation - development mode")
            return True
        return await self._procurement_service.is_valid_account(account_id)

    async def _validate_order(self, order_id: str) -> bool:
        """Validate that the Order ID is valid."""
        if self._settings.skip_jwt_validation:
            logger.warning("Skipping order validation - development mode")
            return True
        return await self._procurement_service.is_valid_order(order_id)

    async def _return_existing_credentials(
        self,
        existing_client: RegisteredClient,
    ) -> DCRResponse | DCRError:
        """Return the existing credentials for an order.

        Per Google's DCR spec: "return the existing client_id and client_secret
        pair for the given order"
        """
        client_secret = self._decrypt_secret(existing_client.client_secret_encrypted)
        if not client_secret:
            logger.error(
                "Failed to decrypt secret for client %s",
                existing_client.client_id,
            )
            return DCRError(
                error=DCRErrorCode.SERVER_ERROR,
                error_description="Failed to retrieve existing credentials",
            )

        return DCRResponse(
            client_id=existing_client.client_id,
            client_secret=client_secret,
            client_secret_expires_at=0,
        )

    async def _create_real_client(
        self,
        claims: GoogleJWTClaims,
    ) -> DCRResponse | DCRError:
        """Create a real OAuth client in Red Hat SSO (Keycloak).

        Args:
            claims: Validated JWT claims.

        Returns:
            DCRResponse with new credentials, or DCRError on failure.
        """
        logger.info(
            "Creating real OAuth client in Keycloak for order: %s",
            claims.order_id,
        )

        try:
            keycloak_client = self._get_keycloak_client()
            response = await keycloak_client.create_client(
                order_id=claims.order_id,
                redirect_uris=claims.auth_app_redirect_uris,
                grant_types=["authorization_code", "refresh_token", "client_credentials"],
            )

            # Encrypt secrets for storage
            encrypted_secret = self._encrypt_secret(response.client_secret)
            encrypted_rat = None
            if response.registration_access_token:
                encrypted_rat = self._encrypt_secret(response.registration_access_token)

            # Store client mapping in database
            await self._client_repository.create(
                client_id=response.client_id,
                client_secret_encrypted=encrypted_secret,
                order_id=claims.order_id,
                account_id=claims.account_id,
                redirect_uris=response.redirect_uris,
                grant_types=["authorization_code", "refresh_token", "client_credentials"],
                registration_access_token_encrypted=encrypted_rat,
                keycloak_client_uuid=None,  # Could extract from registration_client_uri
                metadata={
                    "iss": claims.iss,
                    "aud": claims.aud,
                    "client_name": response.client_name,
                    "registration_client_uri": response.registration_client_uri,
                },
            )

            logger.info(
                "Successfully created OAuth client for order %s: client_id=%s",
                claims.order_id,
                response.client_id,
            )

            return DCRResponse(
                client_id=response.client_id,
                client_secret=response.client_secret,
                client_secret_expires_at=0,
            )

        except KeycloakDCRError as e:
            logger.exception("Keycloak DCR error: %s", e)
            return DCRError(
                error=DCRErrorCode.SERVER_ERROR,
                error_description=f"Failed to create OAuth client: {e}",
            )
        except Exception as e:
            logger.exception("Unexpected error creating client: %s", e)
            return DCRError(
                error=DCRErrorCode.SERVER_ERROR,
                error_description=f"Failed to create client: {e}",
            )

    async def get_client(self, client_id: str) -> RegisteredClient | None:
        """Get a registered client by client_id.

        Args:
            client_id: The OAuth client ID.

        Returns:
            RegisteredClient if found, None otherwise.
        """
        return await self._client_repository.get_by_client_id(client_id)


# Global service instance
_dcr_service: DCRService | None = None


def get_dcr_service() -> DCRService:
    """Get the global DCR service instance.

    Returns:
        DCRService instance.
    """
    global _dcr_service
    if _dcr_service is None:
        _dcr_service = DCRService()
    return _dcr_service
