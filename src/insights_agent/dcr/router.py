"""FastAPI router for Dynamic Client Registration (DCR) endpoint."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from insights_agent.dcr.models import DCRError, DCRRequest, DCRResponse
from insights_agent.dcr.service import DCRService, get_dcr_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["Dynamic Client Registration"])


@router.post(
    "/register",
    response_model=DCRResponse,
    responses={
        400: {"model": DCRError, "description": "Registration failed"},
        500: {"model": DCRError, "description": "Server error"},
    },
)
async def register_client(
    request: Request,
    dcr_request: DCRRequest,
    dcr_service: Annotated[DCRService, Depends(get_dcr_service)],
) -> JSONResponse:
    """Dynamic Client Registration endpoint (RFC 7591).

    This endpoint allows Gemini Enterprise to programmatically register
    as an OAuth 2.0 client with the agent's authorization server.

    The request must contain a `software_statement` JWT signed by Google,
    containing claims about the Gemini Enterprise client including:
    - sub: Procurement Account ID
    - google.order: Marketplace Order ID
    - auth_app_redirect_uris: Redirect URIs for OAuth flow

    On success, returns new OAuth 2.0 client credentials.

    Args:
        request: FastAPI request object.
        dcr_request: DCR request with software_statement.
        dcr_service: DCR service instance.

    Returns:
        DCRResponse with client_id, client_secret, and client_secret_expires_at.

    Raises:
        HTTPException: If registration fails.
    """
    logger.info("Received DCR request from %s", request.client.host if request.client else "unknown")

    result = await dcr_service.register_client(dcr_request)

    if isinstance(result, DCRError):
        logger.warning(
            "DCR request failed: %s - %s",
            result.error,
            result.error_description,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=result.model_dump(exclude_none=True),
        )

    logger.info("DCR request successful: client_id=%s", result.client_id)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=result.model_dump(exclude_none=True),
    )


@router.get("/register/{client_id}")
async def get_client_info(
    client_id: str,
    request: Request,
    dcr_service: Annotated[DCRService, Depends(get_dcr_service)],
) -> JSONResponse:
    """Get registered client information.

    This endpoint returns information about a registered client.
    Authentication is required (not implemented in this version).

    Args:
        client_id: The OAuth client ID.
        request: FastAPI request object.
        dcr_service: DCR service instance.

    Returns:
        Client information (excluding secret).

    Raises:
        HTTPException: If client not found.
    """
    client = await dcr_service.get_client(client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client {client_id} not found",
        )

    # Return client info without secret hash
    return JSONResponse(
        content={
            "client_id": client.client_id,
            "order_id": client.order_id,
            "account_id": client.account_id,
            "redirect_uris": client.redirect_uris,
            "grant_types": client.grant_types,
            "created_at": client.created_at.isoformat(),
        }
    )
