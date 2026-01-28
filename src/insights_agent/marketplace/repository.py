"""Repository for storing and retrieving marketplace accounts and entitlements."""

import hashlib
import logging
import secrets
from datetime import datetime
from typing import Any

from insights_agent.marketplace.models import (
    Account,
    AccountState,
    ClientCredentials,
    Entitlement,
    EntitlementState,
)

logger = logging.getLogger(__name__)


class AccountRepository:
    """Repository for marketplace accounts.

    In production, this should be backed by a database.
    This implementation uses in-memory storage for development.
    """

    def __init__(self) -> None:
        """Initialize the account repository."""
        self._accounts: dict[str, Account] = {}

    async def get(self, account_id: str) -> Account | None:
        """Get an account by ID.

        Args:
            account_id: The Procurement Account ID.

        Returns:
            Account if found, None otherwise.
        """
        return self._accounts.get(account_id)

    async def get_by_provider(self, provider_id: str) -> list[Account]:
        """Get all accounts for a provider.

        Args:
            provider_id: The provider ID.

        Returns:
            List of accounts.
        """
        return [a for a in self._accounts.values() if a.provider_id == provider_id]

    async def create(self, account: Account) -> Account:
        """Create a new account.

        Args:
            account: The account to create.

        Returns:
            The created account.
        """
        self._accounts[account.id] = account
        logger.info("Created account: %s", account.id)
        return account

    async def update(self, account: Account) -> Account:
        """Update an existing account.

        Args:
            account: The account to update.

        Returns:
            The updated account.
        """
        account.updated_at = datetime.utcnow()
        self._accounts[account.id] = account
        logger.info("Updated account: %s (state=%s)", account.id, account.state)
        return account

    async def delete(self, account_id: str) -> bool:
        """Delete an account.

        Args:
            account_id: The account ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        if account_id in self._accounts:
            del self._accounts[account_id]
            logger.info("Deleted account: %s", account_id)
            return True
        return False

    async def exists(self, account_id: str) -> bool:
        """Check if an account exists.

        Args:
            account_id: The account ID.

        Returns:
            True if exists, False otherwise.
        """
        return account_id in self._accounts

    async def is_valid(self, account_id: str) -> bool:
        """Check if an account is valid (exists and active).

        Args:
            account_id: The account ID.

        Returns:
            True if valid, False otherwise.
        """
        account = await self.get(account_id)
        return account is not None and account.state == AccountState.ACTIVE


class EntitlementRepository:
    """Repository for marketplace entitlements (orders).

    In production, this should be backed by a database.
    This implementation uses in-memory storage for development.
    """

    def __init__(self) -> None:
        """Initialize the entitlement repository."""
        self._entitlements: dict[str, Entitlement] = {}
        self._client_id_to_order: dict[str, str] = {}

    async def get(self, entitlement_id: str) -> Entitlement | None:
        """Get an entitlement by ID.

        Args:
            entitlement_id: The Entitlement/Order ID.

        Returns:
            Entitlement if found, None otherwise.
        """
        return self._entitlements.get(entitlement_id)

    async def get_by_account(self, account_id: str) -> list[Entitlement]:
        """Get all entitlements for an account.

        Args:
            account_id: The account ID.

        Returns:
            List of entitlements.
        """
        return [e for e in self._entitlements.values() if e.account_id == account_id]

    async def get_by_client_id(self, client_id: str) -> Entitlement | None:
        """Get an entitlement by OAuth client_id.

        Args:
            client_id: The OAuth client ID.

        Returns:
            Entitlement if found, None otherwise.
        """
        order_id = self._client_id_to_order.get(client_id)
        if order_id:
            return await self.get(order_id)
        return None

    async def get_order_id_by_client_id(self, client_id: str) -> str | None:
        """Get the Order ID associated with a client_id.

        This is used for usage metering to associate usage with orders.

        Args:
            client_id: The OAuth client ID.

        Returns:
            Order ID if found, None otherwise.
        """
        return self._client_id_to_order.get(client_id)

    async def create(self, entitlement: Entitlement) -> Entitlement:
        """Create a new entitlement.

        Args:
            entitlement: The entitlement to create.

        Returns:
            The created entitlement.
        """
        self._entitlements[entitlement.id] = entitlement
        if entitlement.client_id:
            self._client_id_to_order[entitlement.client_id] = entitlement.id
        logger.info(
            "Created entitlement: %s (account=%s)",
            entitlement.id,
            entitlement.account_id,
        )
        return entitlement

    async def update(self, entitlement: Entitlement) -> Entitlement:
        """Update an existing entitlement.

        Args:
            entitlement: The entitlement to update.

        Returns:
            The updated entitlement.
        """
        entitlement.updated_at = datetime.utcnow()
        self._entitlements[entitlement.id] = entitlement
        if entitlement.client_id:
            self._client_id_to_order[entitlement.client_id] = entitlement.id
        logger.info(
            "Updated entitlement: %s (state=%s)",
            entitlement.id,
            entitlement.state,
        )
        return entitlement

    async def delete(self, entitlement_id: str) -> bool:
        """Delete an entitlement.

        Args:
            entitlement_id: The entitlement ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        entitlement = self._entitlements.pop(entitlement_id, None)
        if entitlement:
            if entitlement.client_id:
                self._client_id_to_order.pop(entitlement.client_id, None)
            logger.info("Deleted entitlement: %s", entitlement_id)
            return True
        return False

    async def exists(self, entitlement_id: str) -> bool:
        """Check if an entitlement exists.

        Args:
            entitlement_id: The entitlement ID.

        Returns:
            True if exists, False otherwise.
        """
        return entitlement_id in self._entitlements

    async def is_valid(self, entitlement_id: str) -> bool:
        """Check if an entitlement is valid (exists and active).

        Args:
            entitlement_id: The entitlement ID.

        Returns:
            True if valid, False otherwise.
        """
        entitlement = await self.get(entitlement_id)
        return entitlement is not None and entitlement.state == EntitlementState.ACTIVE

    async def set_client_credentials(
        self,
        entitlement_id: str,
        client_id: str,
        client_secret: str,
    ) -> Entitlement | None:
        """Set OAuth client credentials for an entitlement.

        Args:
            entitlement_id: The entitlement ID.
            client_id: The OAuth client ID.
            client_secret: The OAuth client secret (will be hashed).

        Returns:
            Updated entitlement if found, None otherwise.
        """
        entitlement = await self.get(entitlement_id)
        if not entitlement:
            return None

        # Hash the client secret for storage
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

        entitlement.client_id = client_id
        entitlement.client_secret_hash = secret_hash
        self._client_id_to_order[client_id] = entitlement_id

        return await self.update(entitlement)

    async def generate_client_credentials(
        self,
        entitlement_id: str,
        account_id: str,
    ) -> ClientCredentials | None:
        """Generate new OAuth client credentials for an entitlement.

        Args:
            entitlement_id: The entitlement/order ID.
            account_id: The account ID.

        Returns:
            ClientCredentials with the new credentials, or None if entitlement not found.
        """
        entitlement = await self.get(entitlement_id)
        if not entitlement:
            return None

        # Generate secure client credentials
        client_id = f"client_{secrets.token_urlsafe(16)}"
        client_secret = secrets.token_urlsafe(32)

        # Store credentials in entitlement
        await self.set_client_credentials(entitlement_id, client_id, client_secret)

        return ClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
            order_id=entitlement_id,
            account_id=account_id,
        )

    async def verify_client_secret(
        self,
        client_id: str,
        client_secret: str,
    ) -> bool:
        """Verify a client secret against stored hash.

        Args:
            client_id: The OAuth client ID.
            client_secret: The client secret to verify.

        Returns:
            True if valid, False otherwise.
        """
        entitlement = await self.get_by_client_id(client_id)
        if not entitlement or not entitlement.client_secret_hash:
            return False

        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        return secrets.compare_digest(secret_hash, entitlement.client_secret_hash)


# Global repository instances
_account_repo: AccountRepository | None = None
_entitlement_repo: EntitlementRepository | None = None


def get_account_repository() -> AccountRepository:
    """Get the global account repository instance.

    Returns:
        AccountRepository instance.
    """
    global _account_repo
    if _account_repo is None:
        _account_repo = AccountRepository()
    return _account_repo


def get_entitlement_repository() -> EntitlementRepository:
    """Get the global entitlement repository instance.

    Returns:
        EntitlementRepository instance.
    """
    global _entitlement_repo
    if _entitlement_repo is None:
        _entitlement_repo = EntitlementRepository()
    return _entitlement_repo
