"""Dynamic Client Registration (DCR) module for Google Marketplace integration.

This module implements RFC 7591 Dynamic Client Registration with Google's
software_statement JWT verification for Gemini Enterprise integration.
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
from insights_agent.dcr.service import DCRService, get_dcr_service
from insights_agent.dcr.router import router as dcr_router

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
    # Service
    "DCRService",
    "get_dcr_service",
    # Router
    "dcr_router",
]
