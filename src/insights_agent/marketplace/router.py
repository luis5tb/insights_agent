"""FastAPI router for Marketplace Pub/Sub push endpoint."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from insights_agent.marketplace.pubsub_handler import PubSubHandler, get_pubsub_handler
from insights_agent.marketplace.service import ProcurementService, get_procurement_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


@router.post("/pubsub")
async def handle_pubsub_push(
    request: Request,
    handler: Annotated[PubSubHandler, Depends(get_pubsub_handler)],
) -> dict[str, str]:
    """Handle Pub/Sub push messages from Google Cloud Marketplace.

    This endpoint receives push-style Pub/Sub messages containing
    procurement events (entitlement creation, activation, cancellation, etc.).

    The endpoint should be configured as the push endpoint for the
    Marketplace Pub/Sub subscription.

    Args:
        request: FastAPI request object.
        handler: Pub/Sub handler instance.

    Returns:
        Success acknowledgment.

    Raises:
        HTTPException: If message processing fails.
    """
    try:
        body = await request.json()
        logger.debug("Received Pub/Sub push message")

        success = await handler.handle_push_message(body)

        if success:
            return {"status": "ok"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to process message",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error handling Pub/Sub push: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
) -> dict[str, Any]:
    """Get account information.

    Args:
        account_id: The Procurement Account ID.
        service: Procurement service instance.

    Returns:
        Account information.

    Raises:
        HTTPException: If account not found.
    """
    from insights_agent.marketplace.repository import get_account_repository

    repo = get_account_repository()
    account = await repo.get(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    return account.model_dump()


@router.get("/entitlements/{entitlement_id}")
async def get_entitlement(
    entitlement_id: str,
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
) -> dict[str, Any]:
    """Get entitlement (order) information.

    Args:
        entitlement_id: The Entitlement/Order ID.
        service: Procurement service instance.

    Returns:
        Entitlement information.

    Raises:
        HTTPException: If entitlement not found.
    """
    from insights_agent.marketplace.repository import get_entitlement_repository

    repo = get_entitlement_repository()
    entitlement = await repo.get(entitlement_id)

    if not entitlement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entitlement {entitlement_id} not found",
        )

    # Don't expose client_secret_hash
    result = entitlement.model_dump()
    result.pop("client_secret_hash", None)
    return result


@router.get("/orders/{order_id}/validate")
async def validate_order(
    order_id: str,
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
) -> dict[str, bool]:
    """Validate if an order ID is valid and active.

    This is used by the DCR endpoint to validate orders.

    Args:
        order_id: The Order ID to validate.
        service: Procurement service instance.

    Returns:
        Validation result.
    """
    is_valid = await service.is_valid_order(order_id)
    return {"valid": is_valid, "order_id": order_id}


@router.get("/accounts/{account_id}/validate")
async def validate_account(
    account_id: str,
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
) -> dict[str, bool]:
    """Validate if an account ID is valid and active.

    This is used by the DCR endpoint to validate accounts.

    Args:
        account_id: The Account ID to validate.
        service: Procurement service instance.

    Returns:
        Validation result.
    """
    is_valid = await service.is_valid_account(account_id)
    return {"valid": is_valid, "account_id": account_id}
