"""Dynamic Client Registration (DCR) module for Google Marketplace integration.

This module implements RFC 7591 Dynamic Client Registration with Google's
software_statement JWT verification for Gemini Enterprise integration.

DCR endpoints are served by the marketplace-handler service.
See insights_agent.marketplace_handler.router for the actual routing.
"""

from insights_agent.dcr.models import (
    DCRError,
    DCRErrorCode,
    DCRRequest,
    DCRResponse,
    GoogleJWTClaims,
    RegisteredClient,
)
from insights_agent.dcr.google_jwt import GoogleJWTValidator, get_google_jwt_validator
from insights_agent.dcr.keycloak_client import (
    KeycloakClientResponse,
    KeycloakDCRClient,
    KeycloakDCRError,
    get_keycloak_dcr_client,
)
from insights_agent.dcr.repository import DCRClientRepository, get_dcr_client_repository
from insights_agent.dcr.service import DCRService, get_dcr_service

__all__ = [
    # Models
    "DCRError",
    "DCRErrorCode",
    "DCRRequest",
    "DCRResponse",
    "GoogleJWTClaims",
    "RegisteredClient",
    # JWT Validator
    "GoogleJWTValidator",
    "get_google_jwt_validator",
    # Keycloak Client
    "KeycloakClientResponse",
    "KeycloakDCRClient",
    "KeycloakDCRError",
    "get_keycloak_dcr_client",
    # Repository
    "DCRClientRepository",
    "get_dcr_client_repository",
    # Service
    "DCRService",
    "get_dcr_service",
]
