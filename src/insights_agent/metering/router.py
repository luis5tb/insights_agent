"""API router for metering endpoints."""

import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from insights_agent.auth.dependencies import CurrentUser, require_scope
from insights_agent.metering.metrics import MetricType, UsageSummary
from insights_agent.metering.service import MeteringService, get_metering_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metering", tags=["metering"])


class UsageResponse(BaseModel):
    """Usage query response."""

    order_id: str = Field(..., description="Order ID")
    period_start: datetime = Field(..., description="Start of period")
    period_end: datetime = Field(..., description="End of period")
    metrics: dict[str, int] = Field(default_factory=dict, description="Metric values")
    total_api_calls: int = Field(default=0, description="Total API calls")
    total_tokens: int = Field(default=0, description="Total token usage")
    total_mcp_calls: int = Field(default=0, description="Total MCP tool calls")


class CurrentUsageResponse(BaseModel):
    """Current (all-time) usage response."""

    order_id: str = Field(..., description="Order ID")
    metrics: dict[str, int] = Field(default_factory=dict, description="Metric values")


class BillableUsageResponse(BaseModel):
    """Billable usage response."""

    order_id: str = Field(..., description="Order ID")
    period_start: datetime = Field(..., description="Start of billing period")
    period_end: datetime = Field(..., description="End of billing period")
    billable_metrics: dict[str, int] = Field(
        default_factory=dict, description="Billable metric values"
    )


def get_order_id_from_user(user: CurrentUser) -> str:
    """Extract order ID from authenticated user.

    Args:
        user: Authenticated user.

    Returns:
        Order ID.

    Raises:
        HTTPException: If order ID not found.
    """
    # Order ID should be in the token claims or user metadata
    order_id = user.metadata.get("order_id")
    if not order_id:
        raise HTTPException(
            status_code=403,
            detail="Order ID not found in token",
        )
    return order_id


@router.get(
    "/usage",
    response_model=UsageResponse,
    summary="Get usage summary",
    description="Get usage summary for the authenticated order.",
)
async def get_usage(
    user: Annotated[CurrentUser, Depends(require_scope("metering:read"))],
    start: Annotated[
        datetime | None,
        Query(description="Start of period (default: last hour)"),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="End of period (default: now)"),
    ] = None,
    metering: Annotated[MeteringService, Depends(get_metering_service)] = None,
) -> UsageResponse:
    """Get usage summary for the current order.

    Args:
        user: Authenticated user.
        start: Start of period.
        end: End of period.
        metering: Metering service.

    Returns:
        Usage summary.
    """
    order_id = get_order_id_from_user(user)

    # Default to last hour if not specified
    now = datetime.utcnow()
    start_time = start or (now - timedelta(hours=1))
    end_time = end or now

    summary = await metering.get_usage_summary(order_id, start_time, end_time)

    return UsageResponse(
        order_id=summary.order_id,
        period_start=summary.period_start,
        period_end=summary.period_end,
        metrics=summary.metrics,
        total_api_calls=summary.total_api_calls,
        total_tokens=summary.total_tokens,
        total_mcp_calls=summary.total_mcp_calls,
    )


@router.get(
    "/usage/current",
    response_model=CurrentUsageResponse,
    summary="Get current usage",
    description="Get current (all-time) usage counters for the authenticated order.",
)
async def get_current_usage(
    user: Annotated[CurrentUser, Depends(require_scope("metering:read"))],
    metering: Annotated[MeteringService, Depends(get_metering_service)] = None,
) -> CurrentUsageResponse:
    """Get current usage counters.

    Args:
        user: Authenticated user.
        metering: Metering service.

    Returns:
        Current usage counters.
    """
    order_id = get_order_id_from_user(user)

    metrics = await metering.get_current_usage(order_id)

    return CurrentUsageResponse(
        order_id=order_id,
        metrics=metrics,
    )


@router.get(
    "/usage/billable",
    response_model=BillableUsageResponse,
    summary="Get billable usage",
    description="Get billable usage for a billing period.",
)
async def get_billable_usage(
    user: Annotated[CurrentUser, Depends(require_scope("metering:read"))],
    start: Annotated[datetime, Query(description="Start of billing period")],
    end: Annotated[datetime, Query(description="End of billing period")],
    metering: Annotated[MeteringService, Depends(get_metering_service)] = None,
) -> BillableUsageResponse:
    """Get billable usage for a billing period.

    Args:
        user: Authenticated user.
        start: Start of billing period.
        end: End of billing period.
        metering: Metering service.

    Returns:
        Billable usage.
    """
    order_id = get_order_id_from_user(user)

    billable = await metering.get_billable_usage(order_id, start, end)

    return BillableUsageResponse(
        order_id=order_id,
        period_start=start,
        period_end=end,
        billable_metrics=billable,
    )


# Admin endpoints (internal use only)


class AdminUsageQuery(BaseModel):
    """Admin usage query request."""

    order_id: str = Field(..., description="Order ID to query")
    start: datetime = Field(..., description="Start of period")
    end: datetime = Field(..., description="End of period")


class AllBillableUsageResponse(BaseModel):
    """All billable usage response."""

    period_start: datetime = Field(..., description="Start of billing period")
    period_end: datetime = Field(..., description="End of billing period")
    orders: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="Order ID -> billable metrics"
    )


@router.get(
    "/admin/usage/{order_id}",
    response_model=UsageResponse,
    summary="Get usage for order (admin)",
    description="Admin endpoint to get usage for any order.",
)
async def admin_get_usage(
    order_id: str,
    user: Annotated[CurrentUser, Depends(require_scope("metering:admin"))],
    start: Annotated[
        datetime | None,
        Query(description="Start of period (default: last hour)"),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="End of period (default: now)"),
    ] = None,
    metering: Annotated[MeteringService, Depends(get_metering_service)] = None,
) -> UsageResponse:
    """Get usage summary for any order (admin).

    Args:
        order_id: Order ID to query.
        user: Authenticated admin user.
        start: Start of period.
        end: End of period.
        metering: Metering service.

    Returns:
        Usage summary.
    """
    now = datetime.utcnow()
    start_time = start or (now - timedelta(hours=1))
    end_time = end or now

    summary = await metering.get_usage_summary(order_id, start_time, end_time)

    return UsageResponse(
        order_id=summary.order_id,
        period_start=summary.period_start,
        period_end=summary.period_end,
        metrics=summary.metrics,
        total_api_calls=summary.total_api_calls,
        total_tokens=summary.total_tokens,
        total_mcp_calls=summary.total_mcp_calls,
    )


@router.get(
    "/admin/billable",
    response_model=AllBillableUsageResponse,
    summary="Get all billable usage (admin)",
    description="Admin endpoint to get billable usage for all orders.",
)
async def admin_get_all_billable_usage(
    user: Annotated[CurrentUser, Depends(require_scope("metering:admin"))],
    start: Annotated[datetime, Query(description="Start of billing period")],
    end: Annotated[datetime, Query(description="End of billing period")],
    metering: Annotated[MeteringService, Depends(get_metering_service)] = None,
) -> AllBillableUsageResponse:
    """Get billable usage for all orders (admin).

    Args:
        user: Authenticated admin user.
        start: Start of billing period.
        end: End of billing period.
        metering: Metering service.

    Returns:
        All billable usage.
    """
    all_usage = await metering.get_all_billable_usage(start, end)

    return AllBillableUsageResponse(
        period_start=start,
        period_end=end,
        orders=all_usage,
    )
