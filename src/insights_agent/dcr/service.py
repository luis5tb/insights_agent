"""DCR service for handling Dynamic Client Registration requests."""

import logging
import secrets
import time
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

from insights_agent.config import get_settings
from insights_agent.dcr.google_jwt import GoogleJWTValidator, get_google_jwt_validator
from insights_agent.dcr.models import (
    DCRError,
    DCRErrorCode,
    DCRRequest,
    DCRResponse,
    GoogleJWTClaims,
    RegisteredClient,
)
from insights_agent.marketplace.service import ProcurementService, get_procurement_service

logger = logging.getLogger(__name__)


class DCRService:
    """Service for handling Dynamic Client Registration.

    This service:
    - Validates software_statement JWTs from Google
    - Cross-references with Marketplace Procurement data
    - Creates OAuth client credentials
    - Returns RFC 7591 compliant responses

    Per Google's DCR spec: "You MUST generate a unique client_id and client_secret
    for each 'order' specified in the jwt payload and persist that mapping.
    If an end user creates multiple instances of the agent, return the existing
    client_id and client_secret pair for the given order."
    """

    def __init__(
        self,
        jwt_validator: GoogleJWTValidator | None = None,
        procurement_service: ProcurementService | None = None,
    ) -> None:
        """Initialize the DCR service.

        Args:
            jwt_validator: Google JWT validator (uses default if not provided).
            procurement_service: Procurement service for validation (uses default if not provided).
        """
        self._jwt_validator = jwt_validator or get_google_jwt_validator()
        self._procurement_service = procurement_service or get_procurement_service()
        self._settings = get_settings()
        # In-memory storage for registered clients (use database in production)
        self._registered_clients: dict[str, RegisteredClient] = {}
        # Index by order_id for quick lookup
        self._order_to_client: dict[str, str] = {}
        # Fernet cipher for encrypting client secrets
        self._fernet: Fernet | None = None
        if self._settings.dcr_encryption_key:
            try:
                self._fernet = Fernet(self._settings.dcr_encryption_key.encode())
            except Exception as e:
                logger.error("Invalid DCR encryption key: %s", e)

    def _encrypt_secret(self, secret: str) -> str:
        """Encrypt a client secret for storage.

        Args:
            secret: The plaintext client secret.

        Returns:
            Encrypted secret as base64 string.
        """
        if not self._fernet:
            # Fallback: use a generated key (not recommended for production)
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
        logger.info("Processing DCR request")

        # Step 1: Validate the software_statement JWT
        validation_result = await self._jwt_validator.validate_software_statement(
            request.software_statement
        )

        if isinstance(validation_result, DCRError):
            return validation_result

        claims: GoogleJWTClaims = validation_result

        # Step 2: Validate the Procurement Account ID (sub claim)
        if not await self._validate_account(claims.account_id):
            logger.warning(
                "Invalid Procurement Account ID: %s",
                claims.account_id,
            )
            return DCRError(
                error=DCRErrorCode.UNAPPROVED_SOFTWARE_STATEMENT,
                error_description=f"Invalid Procurement Account ID: {claims.account_id}",
            )

        # Step 3: Validate the Order ID (google.order claim)
        if not await self._validate_order(claims.order_id):
            logger.warning("Invalid Order ID: %s", claims.order_id)
            return DCRError(
                error=DCRErrorCode.UNAPPROVED_SOFTWARE_STATEMENT,
                error_description=f"Invalid Order ID: {claims.order_id}",
            )

        # Step 4: Check if client already exists for this order
        # Per Google's DCR spec: return the SAME credentials for the same order
        existing_client = await self._get_client_by_order(claims.order_id)
        if existing_client:
            logger.info(
                "Returning existing credentials for order: %s (client_id=%s)",
                claims.order_id,
                existing_client.client_id,
            )
            return await self._return_existing_credentials(existing_client)

        # Step 5: Create new OAuth client credentials
        credentials = await self._create_client_credentials(claims)

        if isinstance(credentials, DCRError):
            return credentials

        logger.info(
            "Successfully registered client for order %s: client_id=%s",
            claims.order_id,
            credentials.client_id,
        )

        return credentials

    async def _validate_account(self, account_id: str) -> bool:
        """Validate that the Procurement Account ID is valid.

        Args:
            account_id: The Procurement Account ID from JWT.

        Returns:
            True if valid, False otherwise.
        """
        # Skip validation in development mode
        if self._settings.skip_jwt_validation:
            logger.warning("Skipping account validation - development mode")
            return True

        return await self._procurement_service.is_valid_account(account_id)

    async def _validate_order(self, order_id: str) -> bool:
        """Validate that the Order ID is valid.

        Args:
            order_id: The Order ID from JWT.

        Returns:
            True if valid, False otherwise.
        """
        # Skip validation in development mode
        if self._settings.skip_jwt_validation:
            logger.warning("Skipping order validation - development mode")
            return True

        return await self._procurement_service.is_valid_order(order_id)

    async def _get_client_by_order(self, order_id: str) -> RegisteredClient | None:
        """Get an existing registered client by order ID.

        Args:
            order_id: The Order ID.

        Returns:
            RegisteredClient if exists, None otherwise.
        """
        # Use index for quick lookup
        client_id = self._order_to_client.get(order_id)
        if client_id:
            return self._registered_clients.get(client_id)
        return None

    async def _return_existing_credentials(
        self,
        existing_client: RegisteredClient,
    ) -> DCRResponse | DCRError:
        """Return the existing credentials for an order.

        Per Google's DCR spec: "return the existing client_id and client_secret
        pair for the given order"

        Args:
            existing_client: The existing registered client.

        Returns:
            DCRResponse with the same credentials.
        """
        # Decrypt the stored secret
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

    async def _create_client_credentials(
        self,
        claims: GoogleJWTClaims,
    ) -> DCRResponse | DCRError:
        """Create new OAuth client credentials.

        Args:
            claims: Validated JWT claims.

        Returns:
            DCRResponse with new credentials, or DCRError on failure.
        """
        try:
            # Generate unique client_id and client_secret
            # Use order ID in client_id for easier debugging (per Google example)
            client_id = f"client_{claims.order_id}"
            client_secret = secrets.token_urlsafe(32)
            encrypted_secret = self._encrypt_secret(client_secret)
            issued_at = int(time.time())

            # Create registered client record
            registered_client = RegisteredClient(
                client_id=client_id,
                client_secret_encrypted=encrypted_secret,
                order_id=claims.order_id,
                account_id=claims.account_id,
                redirect_uris=claims.auth_app_redirect_uris,
                grant_types=["authorization_code", "refresh_token"],
                created_at=datetime.utcnow(),
                metadata={
                    "iss": claims.iss,
                    "aud": claims.aud,
                    "registered_at": issued_at,
                },
            )

            # Store client with order index
            self._registered_clients[client_id] = registered_client
            self._order_to_client[claims.order_id] = client_id

            # Also update the entitlement in procurement service
            # This creates the client_id -> order_id mapping for usage metering
            from insights_agent.marketplace.repository import get_entitlement_repository

            entitlement_repo = get_entitlement_repository()
            await entitlement_repo.set_client_credentials(
                entitlement_id=claims.order_id,
                client_id=client_id,
                client_secret=client_secret,
            )

            # Return only the 3 required fields per Google's example
            return DCRResponse(
                client_id=client_id,
                client_secret=client_secret,
                client_secret_expires_at=0,
            )

        except Exception as e:
            logger.exception("Failed to create client credentials: %s", e)
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
        return self._registered_clients.get(client_id)

    async def verify_client(self, client_id: str, client_secret: str) -> bool:
        """Verify client credentials.

        Args:
            client_id: The OAuth client ID.
            client_secret: The OAuth client secret.

        Returns:
            True if valid, False otherwise.
        """
        client = self._registered_clients.get(client_id)
        if not client:
            return False

        stored_secret = self._decrypt_secret(client.client_secret_encrypted)
        if not stored_secret:
            return False

        return secrets.compare_digest(client_secret, stored_secret)

    async def get_order_id_for_client(self, client_id: str) -> str | None:
        """Get the Order ID associated with a client_id.

        Used for usage metering.

        Args:
            client_id: The OAuth client ID.

        Returns:
            Order ID if found, None otherwise.
        """
        client = self._registered_clients.get(client_id)
        return client.order_id if client else None


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
