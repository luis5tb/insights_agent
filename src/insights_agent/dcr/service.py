"""DCR service for handling Dynamic Client Registration requests."""

import hashlib
import logging
import secrets
import time
from datetime import datetime

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
        existing_client = await self._get_client_by_order(claims.order_id)
        if existing_client:
            # Return existing credentials (generate new secret for security)
            logger.info(
                "Regenerating credentials for existing order: %s",
                claims.order_id,
            )
            return await self._regenerate_credentials(
                existing_client,
                claims.auth_app_redirect_uris,
            )

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
        for client in self._registered_clients.values():
            if client.order_id == order_id:
                return client
        return None

    async def _regenerate_credentials(
        self,
        existing_client: RegisteredClient,
        redirect_uris: list[str],
    ) -> DCRResponse:
        """Regenerate credentials for an existing client.

        Per DCR spec, we can return new credentials for the same order.

        Args:
            existing_client: The existing registered client.
            redirect_uris: New redirect URIs from the request.

        Returns:
            DCRResponse with new credentials.
        """
        # Generate new secret
        client_secret = secrets.token_urlsafe(32)
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

        # Update client
        existing_client.client_secret_hash = secret_hash
        existing_client.redirect_uris = redirect_uris
        self._registered_clients[existing_client.client_id] = existing_client

        # Update procurement service mapping
        await self._procurement_service.get_or_create_client_credentials(
            existing_client.order_id
        )

        return DCRResponse(
            client_id=existing_client.client_id,
            client_secret=client_secret,
            client_secret_expires_at=0,
            client_id_issued_at=int(existing_client.created_at.timestamp()),
            redirect_uris=redirect_uris,
            grant_types=existing_client.grant_types,
            token_endpoint_auth_method="client_secret_basic",
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
            client_id = f"gemini_{secrets.token_urlsafe(16)}"
            client_secret = secrets.token_urlsafe(32)
            secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
            issued_at = int(time.time())

            # Create registered client record
            registered_client = RegisteredClient(
                client_id=client_id,
                client_secret_hash=secret_hash,
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

            # Store client
            self._registered_clients[client_id] = registered_client

            # Also update the entitlement in procurement service
            # This creates the client_id -> order_id mapping for usage metering
            from insights_agent.marketplace.repository import get_entitlement_repository

            entitlement_repo = get_entitlement_repository()
            await entitlement_repo.set_client_credentials(
                entitlement_id=claims.order_id,
                client_id=client_id,
                client_secret=client_secret,
            )

            return DCRResponse(
                client_id=client_id,
                client_secret=client_secret,
                client_secret_expires_at=0,
                client_id_issued_at=issued_at,
                redirect_uris=claims.auth_app_redirect_uris,
                grant_types=["authorization_code", "refresh_token"],
                token_endpoint_auth_method="client_secret_basic",
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

        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        return secrets.compare_digest(secret_hash, client.client_secret_hash)

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
