"""Tests for Dynamic Client Registration (DCR) implementation."""

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from insights_agent.api.app import create_app
from insights_agent.dcr.models import (
    DCRError,
    DCRErrorCode,
    DCRRequest,
    DCRResponse,
    GoogleClaims,
    GoogleJWTClaims,
    RegisteredClient,
)
from insights_agent.dcr.service import DCRService
from insights_agent.marketplace.models import Account, AccountState, Entitlement, EntitlementState
from insights_agent.marketplace.repository import AccountRepository, EntitlementRepository
from insights_agent.marketplace.service import ProcurementService


class TestModels:
    """Tests for DCR data models."""

    def test_google_jwt_claims(self):
        """Test parsing Google JWT claims."""
        claims_data = {
            "iss": "https://www.googleapis.com/service_accounts/v1/metadata/x509/cloud-agentspace@system.gserviceaccount.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "aud": "https://example.com",
            "sub": "account-123",
            "auth_app_redirect_uris": ["https://example.com/callback"],
            "google": {"order": "order-456"},
        }

        claims = GoogleJWTClaims(**claims_data)

        assert claims.iss == claims_data["iss"]
        assert claims.account_id == "account-123"
        assert claims.order_id == "order-456"
        assert claims.auth_app_redirect_uris == ["https://example.com/callback"]

    def test_google_jwt_claims_extra_fields(self):
        """Test that extra fields are allowed (per spec)."""
        claims_data = {
            "iss": "https://example.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "aud": "https://example.com",
            "sub": "account-123",
            "google": {"order": "order-456"},
            "unknown_field": "should be allowed",
        }

        claims = GoogleJWTClaims(**claims_data)

        assert claims.account_id == "account-123"

    def test_dcr_request(self):
        """Test DCR request model."""
        request = DCRRequest(software_statement="eyJ...")

        assert request.software_statement == "eyJ..."

    def test_dcr_response(self):
        """Test DCR response model."""
        response = DCRResponse(
            client_id="client_abc123",
            client_secret="secret_xyz789",
            client_secret_expires_at=0,
        )

        assert response.client_id == "client_abc123"
        assert response.client_secret == "secret_xyz789"
        assert response.client_secret_expires_at == 0

    def test_dcr_error(self):
        """Test DCR error model."""
        error = DCRError(
            error=DCRErrorCode.INVALID_SOFTWARE_STATEMENT,
            error_description="JWT has expired",
        )

        assert error.error == DCRErrorCode.INVALID_SOFTWARE_STATEMENT
        assert "expired" in error.error_description

    def test_registered_client(self):
        """Test RegisteredClient model."""
        client = RegisteredClient(
            client_id="client_123",
            client_secret_hash="hash_abc",
            order_id="order-456",
            account_id="account-789",
            redirect_uris=["https://example.com/callback"],
        )

        assert client.client_id == "client_123"
        assert client.order_id == "order-456"
        assert "authorization_code" in client.grant_types


class TestDCRService:
    """Tests for DCR service."""

    @pytest.fixture
    def service(self):
        """Create a fresh DCR service with mocked dependencies."""
        account_repo = AccountRepository()
        entitlement_repo = EntitlementRepository()
        procurement_service = ProcurementService(
            account_repo=account_repo,
            entitlement_repo=entitlement_repo,
        )

        # Pre-populate with valid account and order
        import asyncio

        async def setup():
            account = Account(
                id="valid-account-123",
                provider_id="provider-456",
                state=AccountState.ACTIVE,
            )
            await account_repo.create(account)

            entitlement = Entitlement(
                id="valid-order-789",
                account_id="valid-account-123",
                provider_id="provider-456",
                state=EntitlementState.ACTIVE,
            )
            await entitlement_repo.create(entitlement)

        asyncio.get_event_loop().run_until_complete(setup())

        return DCRService(procurement_service=procurement_service)

    @pytest.mark.asyncio
    async def test_get_order_id_for_client(self, service):
        """Test looking up order ID by client ID."""
        # First register a client
        from insights_agent.dcr.models import GoogleJWTClaims

        claims = GoogleJWTClaims(
            iss="https://example.com",
            iat=int(time.time()),
            exp=int(time.time()) + 3600,
            aud="https://example.com",
            sub="valid-account-123",
            auth_app_redirect_uris=["https://example.com/callback"],
            google=GoogleClaims(order="valid-order-789"),
        )

        # Create credentials directly
        result = await service._create_client_credentials(claims)

        assert isinstance(result, DCRResponse)

        # Verify we can look up the order ID
        order_id = await service.get_order_id_for_client(result.client_id)
        assert order_id == "valid-order-789"

    @pytest.mark.asyncio
    async def test_verify_client(self, service):
        """Test client verification."""
        from insights_agent.dcr.models import GoogleJWTClaims

        claims = GoogleJWTClaims(
            iss="https://example.com",
            iat=int(time.time()),
            exp=int(time.time()) + 3600,
            aud="https://example.com",
            sub="valid-account-123",
            google=GoogleClaims(order="valid-order-789"),
        )

        result = await service._create_client_credentials(claims)
        assert isinstance(result, DCRResponse)

        # Verify with correct secret
        is_valid = await service.verify_client(result.client_id, result.client_secret)
        assert is_valid is True

        # Verify with wrong secret
        is_valid = await service.verify_client(result.client_id, "wrong-secret")
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_get_client(self, service):
        """Test getting client info."""
        from insights_agent.dcr.models import GoogleJWTClaims

        claims = GoogleJWTClaims(
            iss="https://example.com",
            iat=int(time.time()),
            exp=int(time.time()) + 3600,
            aud="https://example.com",
            sub="valid-account-123",
            google=GoogleClaims(order="valid-order-789"),
        )

        result = await service._create_client_credentials(claims)
        assert isinstance(result, DCRResponse)

        client = await service.get_client(result.client_id)
        assert client is not None
        assert client.order_id == "valid-order-789"
        assert client.account_id == "valid-account-123"


class TestDCRRouter:
    """Tests for DCR API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app)

    def test_register_endpoint_invalid_jwt(self, client):
        """Test register endpoint with invalid JWT."""
        response = client.post(
            "/oauth/register",
            json={"software_statement": "invalid-jwt-token"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_software_statement"

    def test_register_endpoint_missing_software_statement(self, client):
        """Test register endpoint with missing software_statement."""
        response = client.post(
            "/oauth/register",
            json={},
        )

        assert response.status_code == 422  # Validation error

    def test_get_client_not_found(self, client):
        """Test getting nonexistent client."""
        response = client.get("/oauth/register/nonexistent-client")

        assert response.status_code == 404


class TestAgentCardDCRExtension:
    """Tests for DCR extension in AgentCard."""

    def test_agent_card_has_dcr_extension(self):
        """Test that AgentCard includes DCR extension."""
        from insights_agent.api.a2a.agent_card import build_agent_card

        card = build_agent_card()

        # Extensions are now a list of AgentExtension objects
        assert card.capabilities.extensions is not None
        assert len(card.capabilities.extensions) > 0
        dcr_ext = card.capabilities.extensions[0]
        assert "dcr" in dcr_ext.uri
        assert dcr_ext.params is not None
        assert "endpoint" in dcr_ext.params
        assert "/oauth/register" in dcr_ext.params["endpoint"]

    def test_agent_card_endpoint_returns_dcr(self):
        """Test that AgentCard endpoint includes DCR extension."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/.well-known/agent.json")

        assert response.status_code == 200
        data = response.json()
        assert "capabilities" in data
        assert "extensions" in data["capabilities"]
        # Extensions are now a list
        extensions = data["capabilities"]["extensions"]
        assert len(extensions) > 0
        dcr_ext = extensions[0]
        assert "dcr" in dcr_ext["uri"]
        assert "endpoint" in dcr_ext["params"]
