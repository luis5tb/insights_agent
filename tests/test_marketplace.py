"""Tests for Marketplace Procurement integration."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from insights_agent.api.app import create_app
from insights_agent.marketplace.models import (
    Account,
    AccountState,
    Entitlement,
    EntitlementState,
    ProcurementEvent,
    ProcurementEventType,
)
from insights_agent.marketplace.repository import (
    AccountRepository,
    EntitlementRepository,
)
from insights_agent.marketplace.service import ProcurementService


class TestModels:
    """Tests for marketplace data models."""

    def test_procurement_event_parsing(self):
        """Test parsing a procurement event."""
        event_data = {
            "eventId": "event-123",
            "eventType": "ENTITLEMENT_ACTIVE",
            "providerId": "provider-123",
            "entitlement": {
                "id": "entitlement-456",
                "updateTime": "2024-01-01T00:00:00Z",
            },
        }

        event = ProcurementEvent(**event_data)

        assert event.event_id == "event-123"
        assert event.event_type == ProcurementEventType.ENTITLEMENT_ACTIVE
        assert event.provider_id == "provider-123"
        assert event.entitlement.id == "entitlement-456"

    def test_account_event_parsing(self):
        """Test parsing an account event."""
        event_data = {
            "eventId": "event-789",
            "eventType": "ACCOUNT_ACTIVE",
            "providerId": "provider-123",
            "account": {
                "id": "account-456",
            },
        }

        event = ProcurementEvent(**event_data)

        assert event.event_type == ProcurementEventType.ACCOUNT_ACTIVE
        assert event.account.id == "account-456"

    def test_all_event_types_valid(self):
        """Test all event types are valid enum values."""
        event_types = [
            "ACCOUNT_ACTIVE",
            "ACCOUNT_DELETED",
            "ENTITLEMENT_CREATION_REQUESTED",
            "ENTITLEMENT_ACTIVE",
            "ENTITLEMENT_CANCELLED",
        ]

        for event_type in event_types:
            assert ProcurementEventType(event_type) is not None


class TestAccountRepository:
    """Tests for account repository."""

    @pytest.fixture
    def repo(self):
        """Create a fresh repository."""
        return AccountRepository()

    @pytest.mark.asyncio
    async def test_create_account(self, repo):
        """Test creating an account."""
        account = Account(
            id="account-123",
            provider_id="provider-456",
            state=AccountState.ACTIVE,
        )

        created = await repo.create(account)

        assert created.id == "account-123"
        assert await repo.exists("account-123")

    @pytest.mark.asyncio
    async def test_get_account(self, repo):
        """Test getting an account."""
        account = Account(id="account-123", provider_id="provider-456")
        await repo.create(account)

        retrieved = await repo.get("account-123")

        assert retrieved is not None
        assert retrieved.id == "account-123"

    @pytest.mark.asyncio
    async def test_get_nonexistent_account(self, repo):
        """Test getting a nonexistent account."""
        result = await repo.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_account(self, repo):
        """Test updating an account."""
        account = Account(
            id="account-123",
            provider_id="provider-456",
            state=AccountState.PENDING,
        )
        await repo.create(account)

        account.state = AccountState.ACTIVE
        updated = await repo.update(account)

        assert updated.state == AccountState.ACTIVE

    @pytest.mark.asyncio
    async def test_is_valid_account(self, repo):
        """Test account validity check."""
        account = Account(
            id="account-123",
            provider_id="provider-456",
            state=AccountState.ACTIVE,
        )
        await repo.create(account)

        assert await repo.is_valid("account-123") is True
        assert await repo.is_valid("nonexistent") is False


class TestEntitlementRepository:
    """Tests for entitlement repository."""

    @pytest.fixture
    def repo(self):
        """Create a fresh repository."""
        return EntitlementRepository()

    @pytest.mark.asyncio
    async def test_create_entitlement(self, repo):
        """Test creating an entitlement."""
        entitlement = Entitlement(
            id="order-123",
            account_id="account-456",
            provider_id="provider-789",
            state=EntitlementState.ACTIVE,
        )

        created = await repo.create(entitlement)

        assert created.id == "order-123"
        assert await repo.exists("order-123")

    @pytest.mark.asyncio
    async def test_get_by_account(self, repo):
        """Test getting entitlements by account."""
        for i in range(3):
            entitlement = Entitlement(
                id=f"order-{i}",
                account_id="account-123",
                provider_id="provider-456",
            )
            await repo.create(entitlement)

        entitlements = await repo.get_by_account("account-123")

        assert len(entitlements) == 3

    @pytest.mark.asyncio
    async def test_generate_client_credentials(self, repo):
        """Test generating OAuth credentials."""
        entitlement = Entitlement(
            id="order-123",
            account_id="account-456",
            provider_id="provider-789",
        )
        await repo.create(entitlement)

        credentials = await repo.generate_client_credentials(
            entitlement_id="order-123",
            account_id="account-456",
        )

        assert credentials is not None
        assert credentials.client_id.startswith("client_")
        assert credentials.order_id == "order-123"

    @pytest.mark.asyncio
    async def test_get_order_id_by_client_id(self, repo):
        """Test looking up order ID by client ID."""
        entitlement = Entitlement(
            id="order-123",
            account_id="account-456",
            provider_id="provider-789",
        )
        await repo.create(entitlement)

        credentials = await repo.generate_client_credentials(
            entitlement_id="order-123",
            account_id="account-456",
        )

        order_id = await repo.get_order_id_by_client_id(credentials.client_id)

        assert order_id == "order-123"


class TestProcurementService:
    """Tests for procurement service."""

    @pytest.fixture
    def service(self):
        """Create a fresh service."""
        return ProcurementService(
            account_repo=AccountRepository(),
            entitlement_repo=EntitlementRepository(),
        )

    @pytest.mark.asyncio
    async def test_process_account_active(self, service):
        """Test processing ACCOUNT_ACTIVE event."""
        event = ProcurementEvent(
            event_id="event-123",
            event_type=ProcurementEventType.ACCOUNT_ACTIVE,
            provider_id="provider-123",
            account={"id": "account-456"},
        )

        await service.process_event(event)

        assert await service.is_valid_account("account-456")

    @pytest.mark.asyncio
    async def test_process_entitlement_active(self, service):
        """Test processing ENTITLEMENT_ACTIVE event."""
        event = ProcurementEvent(
            event_id="event-123",
            event_type=ProcurementEventType.ENTITLEMENT_ACTIVE,
            provider_id="provider-123",
            entitlement={"id": "order-456"},
        )

        await service.process_event(event)

        assert await service.is_valid_order("order-456")

    @pytest.mark.asyncio
    async def test_get_or_create_credentials(self, service):
        """Test getting or creating credentials for an order."""
        # First create an active entitlement
        event = ProcurementEvent(
            event_id="event-123",
            event_type=ProcurementEventType.ENTITLEMENT_ACTIVE,
            provider_id="provider-123",
            entitlement={"id": "order-456"},
        )
        await service.process_event(event)

        credentials = await service.get_or_create_client_credentials("order-456")

        assert credentials is not None
        assert credentials.order_id == "order-456"


class TestMarketplaceRouter:
    """Tests for marketplace API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app)

    def test_pubsub_push_endpoint(self, client):
        """Test Pub/Sub push endpoint."""
        event_data = {
            "eventId": "event-123",
            "eventType": "ACCOUNT_ACTIVE",
            "providerId": "provider-123",
            "account": {"id": "account-456"},
        }
        encoded_data = base64.b64encode(json.dumps(event_data).encode()).decode()

        push_body = {
            "message": {
                "data": encoded_data,
                "messageId": "msg-123",
                "publishTime": "2024-01-01T00:00:00Z",
            },
        }

        response = client.post("/marketplace/pubsub", json=push_body)

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_validate_order_not_found(self, client):
        """Test order validation for nonexistent order."""
        response = client.get("/marketplace/orders/nonexistent/validate")

        assert response.status_code == 200
        assert response.json()["valid"] is False

    def test_validate_account_not_found(self, client):
        """Test account validation for nonexistent account."""
        response = client.get("/marketplace/accounts/nonexistent/validate")

        assert response.status_code == 200
        assert response.json()["valid"] is False
