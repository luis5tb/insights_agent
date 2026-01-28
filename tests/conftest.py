"""Pytest configuration and fixtures."""

import os

import pytest

# Set test environment variables before importing application modules
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
os.environ["GOOGLE_API_KEY"] = "test-api-key"
os.environ["LIGHTSPEED_CLIENT_ID"] = "test-client-id"
os.environ["LIGHTSPEED_CLIENT_SECRET"] = "test-client-secret"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DEBUG"] = "true"
os.environ["SKIP_JWT_VALIDATION"] = "true"


@pytest.fixture
def test_settings():
    """Provide test settings."""
    from insights_agent.config import Settings

    return Settings(
        google_api_key="test-api-key",
        lightspeed_client_id="test-client-id",
        lightspeed_client_secret="test-client-secret",
        database_url="sqlite+aiosqlite:///:memory:",
        debug=True,
        skip_jwt_validation=True,
    )
