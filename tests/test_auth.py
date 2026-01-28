"""Tests for authentication and authorization module."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from insights_agent.auth import (
    AuthenticatedUser,
    JWTValidator,
    OAuthClient,
    TokenResponse,
    oauth_router,
)
from insights_agent.config import Settings


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        red_hat_sso_issuer="https://sso.redhat.com/auth/realms/redhat-external",
        red_hat_sso_client_id="test-client-id",
        red_hat_sso_client_secret="test-client-secret",
        red_hat_sso_redirect_uri="http://localhost:8000/oauth/callback",
        red_hat_sso_jwks_uri="https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs",
        skip_jwt_validation=True,
        debug=True,
    )


@pytest.fixture
def oauth_client(mock_settings):
    """Create OAuth client for testing."""
    return OAuthClient(settings=mock_settings)


@pytest.fixture
def jwt_validator(mock_settings):
    """Create JWT validator for testing."""
    return JWTValidator(settings=mock_settings)


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


class TestJWTValidator:
    """Tests for JWTValidator."""

    @pytest.mark.asyncio
    async def test_validate_token_dev_mode(self, jwt_validator):
        """Test token validation in development mode (skipped)."""
        # Create a simple JWT for testing (won't be fully validated in dev mode)
        claims = {
            "iss": "https://sso.redhat.com/auth/realms/redhat-external",
            "sub": "test-user-id",
            "aud": "test-client-id",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "azp": "test-client-id",
            "preferred_username": "testuser",
            "email": "test@example.com",
        }

        # Create a fake token (we're in skip validation mode)
        token = jwt.encode(claims, "secret", algorithm="HS256")

        user = await jwt_validator.validate_token(token)

        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == "test-user-id"
        assert user.client_id == "test-client-id"
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_validate_token_dev_mode_fallback(self, jwt_validator):
        """Test token validation fallback for invalid tokens in dev mode."""
        user = await jwt_validator.validate_token("invalid-token")

        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == "dev-user"
        assert user.client_id == "dev-client"


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
