"""Tests for authentication and authorization module."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lightspeed_agent.auth import (
    AuthenticatedUser,
    OAuthClient,
    TokenResponse,
    oauth_router,
)
from lightspeed_agent.auth.introspection import (
    InsufficientScopeError,
    TokenIntrospector,
    TokenValidationError,
)
from lightspeed_agent.config import Settings


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        red_hat_sso_issuer="https://sso.redhat.com/auth/realms/redhat-external",
        red_hat_sso_client_id="test-client-id",
        red_hat_sso_client_secret="test-client-secret",
        red_hat_sso_redirect_uri="http://localhost:8000/oauth/callback",
        agent_required_scope="agent:insights",
        skip_jwt_validation=False,
        debug=True,
    )


@pytest.fixture
def dev_settings():
    """Create settings with skip_jwt_validation=True."""
    return Settings(
        red_hat_sso_issuer="https://sso.redhat.com/auth/realms/redhat-external",
        red_hat_sso_client_id="test-client-id",
        red_hat_sso_client_secret="test-client-secret",
        red_hat_sso_redirect_uri="http://localhost:8000/oauth/callback",
        agent_required_scope="agent:insights",
        skip_jwt_validation=True,
        debug=True,
    )


@pytest.fixture
def oauth_client(mock_settings):
    """Create OAuth client for testing."""
    return OAuthClient(settings=mock_settings)


@pytest.fixture
def introspector(mock_settings):
    """Create token introspector for testing."""
    return TokenIntrospector(settings=mock_settings)


@pytest.fixture
def dev_introspector(dev_settings):
    """Create token introspector in dev mode."""
    return TokenIntrospector(settings=dev_settings)


@pytest.fixture
def test_app():
    """Create test FastAPI app with OAuth router."""
    app = FastAPI()
    app.include_router(oauth_router)
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestOAuthClient:
    """Tests for OAuthClient."""

    def test_authorization_endpoint(self, oauth_client):
        """Test authorization endpoint URL construction."""
        assert oauth_client.authorization_endpoint == (
            "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/auth"
        )

    def test_token_endpoint(self, oauth_client):
        """Test token endpoint URL construction."""
        assert oauth_client.token_endpoint == (
            "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
        )

    def test_generate_state(self, oauth_client):
        """Test state parameter generation."""
        state1 = oauth_client.generate_state()
        state2 = oauth_client.generate_state()

        assert len(state1) > 20
        assert state1 != state2

    def test_build_authorization_url(self, oauth_client):
        """Test authorization URL building."""
        state = "test-state-12345"
        url = oauth_client.build_authorization_url(state=state)

        assert "response_type=code" in url
        assert f"client_id={oauth_client.client_id}" in url
        assert f"state={state}" in url
        assert "scope=openid+profile+email" in url

    def test_build_authorization_url_custom_scope(self, oauth_client):
        """Test authorization URL with custom scope."""
        url = oauth_client.build_authorization_url(state="test", scope="openid")

        assert "scope=openid" in url

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, oauth_client):
        """Test successful code exchange."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "test-refresh-token",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await oauth_client.exchange_code("test-code")

            assert isinstance(result, TokenResponse)
            assert result.access_token == "test-access-token"
            assert result.refresh_token == "test-refresh-token"

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, oauth_client):
        """Test successful token refresh."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "new-refresh-token",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await oauth_client.refresh_token("old-refresh-token")

            assert isinstance(result, TokenResponse)
            assert result.access_token == "new-access-token"


class TestTokenIntrospector:
    """Tests for TokenIntrospector (token introspection)."""

    @pytest.mark.asyncio
    async def test_active_token_with_scope(self, introspector):
        """Test validating an active token with the required scope."""
        introspection_response = {
            "active": True,
            "sub": "user-123",
            "client_id": "gemini-order-abc",
            "scope": "openid agent:insights",
            "preferred_username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "exp": int(time.time()) + 3600,
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = introspection_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            user = await introspector.validate_token("some-token")

            assert isinstance(user, AuthenticatedUser)
            assert user.user_id == "user-123"
            assert user.client_id == "gemini-order-abc"
            assert user.email == "test@example.com"
            assert "agent:insights" in user.scopes
            assert "openid" in user.scopes

    @pytest.mark.asyncio
    async def test_inactive_token(self, introspector):
        """Test that an inactive token raises TokenValidationError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"active": False}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            with pytest.raises(TokenValidationError, match="not active"):
                await introspector.validate_token("expired-token")

    @pytest.mark.asyncio
    async def test_missing_scope(self, introspector):
        """Test that a token without the required scope raises InsufficientScopeError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "active": True,
            "sub": "user-123",
            "scope": "openid profile",
            "exp": int(time.time()) + 3600,
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            with pytest.raises(InsufficientScopeError, match="agent:insights"):
                await introspector.validate_token("no-scope-token")

    @pytest.mark.asyncio
    async def test_introspection_http_error(self, introspector):
        """Test that HTTP errors from introspection raise TokenValidationError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            with pytest.raises(TokenValidationError, match="HTTP 500"):
                await introspector.validate_token("some-token")

    @pytest.mark.asyncio
    async def test_introspection_network_error(self, introspector):
        """Test that network errors raise TokenValidationError."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = httpx.ConnectError("Connection refused")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            with pytest.raises(TokenValidationError, match="HTTP error"):
                await introspector.validate_token("some-token")

    @pytest.mark.asyncio
    async def test_dev_mode_returns_dev_user(self, dev_introspector):
        """Test that dev mode returns a default user with agent:insights scope."""
        user = await dev_introspector.validate_token("any-token")

        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == "dev-user"
        assert user.client_id == "dev-client"
        assert "agent:insights" in user.scopes

    @pytest.mark.asyncio
    async def test_azp_preferred_over_client_id(self, introspector):
        """Test that azp is used over client_id when both are present."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "active": True,
            "sub": "user-123",
            "azp": "azp-client",
            "client_id": "other-client",
            "scope": "openid agent:insights",
            "exp": int(time.time()) + 3600,
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            user = await introspector.validate_token("some-token")
            assert user.client_id == "azp-client"


class TestOAuthRouter:
    """Tests for OAuth router endpoints."""

    def test_authorize_redirect(self, client):
        """Test authorization endpoint redirects to IdP."""
        response = client.get(
            "/oauth/authorize",
            params={"client_id": "test", "redirect_uri": "http://localhost/callback"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers.get("location")
        assert "sso.redhat.com" in location
        assert "response_type=code" in location

    def test_callback_missing_code(self, client):
        """Test callback endpoint requires code."""
        response = client.get("/oauth/callback", params={"state": "test-state"})

        assert response.status_code == 400

    def test_callback_missing_state(self, client):
        """Test callback endpoint validates state."""
        response = client.get("/oauth/callback", params={"code": "test-code"})

        assert response.status_code == 400

    def test_token_unsupported_grant_type(self, client):
        """Test token endpoint rejects unsupported grant types."""
        response = client.post(
            "/oauth/token",
            data={"grant_type": "password"},
        )

        assert response.status_code == 400
        assert "Unsupported grant type" in response.text

    def test_token_missing_code(self, client):
        """Test token endpoint requires code for authorization_code grant."""
        response = client.post(
            "/oauth/token",
            data={"grant_type": "authorization_code"},
        )

        assert response.status_code == 400
        assert "Missing authorization code" in response.text

    def test_token_missing_refresh_token(self, client):
        """Test token endpoint requires refresh_token for refresh grant."""
        response = client.post(
            "/oauth/token",
            data={"grant_type": "refresh_token"},
        )

        assert response.status_code == 400
        assert "Missing refresh token" in response.text

    def test_userinfo_missing_auth(self, client):
        """Test userinfo endpoint requires authentication."""
        response = client.get("/oauth/userinfo")

        assert response.status_code == 401


class TestAuthenticatedUser:
    """Tests for AuthenticatedUser model."""

    def test_authenticated_user_creation(self):
        """Test AuthenticatedUser model creation."""
        user = AuthenticatedUser(
            user_id="user-123",
            client_id="client-456",
            username="testuser",
            email="test@example.com",
            name="Test User",
            org_id="org-789",
            scopes=["openid", "profile", "email"],
            token_exp=datetime.now(UTC),
        )

        assert user.user_id == "user-123"
        assert user.client_id == "client-456"
        assert "openid" in user.scopes
