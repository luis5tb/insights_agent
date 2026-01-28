"""Metering service for tracking and managing usage."""

import logging
from datetime import datetime, timedelta
from typing import Any

from insights_agent.config import get_settings
from insights_agent.metering.metrics import (
    MetricType,
    UsageRecord,
    UsageSummary,
)
from insights_agent.metering.repository import UsageRepository, get_usage_repository

logger = logging.getLogger(__name__)


class MeteringService:
    """Service for tracking usage and managing metering.

    This service:
    - Records usage metrics per order
    - Looks up order IDs from client IDs
    - Provides usage summaries for reporting
    - Tracks token usage from agent responses
    """

    def __init__(
        self,
        usage_repo: UsageRepository | None = None,
    ) -> None:
        """Initialize the metering service.

        Args:
            usage_repo: Usage repository (uses default if not provided).
        """
        self._usage_repo = usage_repo or get_usage_repository()
        self._settings = get_settings()

    async def track_api_call(
        self,
        order_id: str,
        client_id: str | None = None,
        context_id: str | None = None,
        task_id: str | None = None,
        streaming: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Track an API call.

        Args:
            order_id: The Order ID.
            client_id: OAuth client ID.
            context_id: Conversation context ID.
            task_id: Associated task ID.
            streaming: Whether this is a streaming request.
            metadata: Additional metadata.

        Returns:
            The created usage record.
        """
        metric_type = (
            MetricType.STREAMING_REQUESTS if streaming else MetricType.SEND_MESSAGE_REQUESTS
        )

        # Record the specific request type
        await self._usage_repo.record_metric(
            order_id=order_id,
            metric_type=metric_type,
            client_id=client_id,
            context_id=context_id,
            task_id=task_id,
            metadata=metadata,
        )

        # Also record as general API call
        return await self._usage_repo.record_metric(
            order_id=order_id,
            metric_type=MetricType.API_CALLS,
            client_id=client_id,
            context_id=context_id,
            task_id=task_id,
            metadata=metadata,
        )

    async def track_token_usage(
        self,
        order_id: str,
        input_tokens: int,
        output_tokens: int,
        client_id: str | None = None,
        context_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Track token usage.

        Args:
            order_id: The Order ID.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            client_id: OAuth client ID.
            context_id: Conversation context ID.
            task_id: Associated task ID.
            metadata: Additional metadata.
        """
        if input_tokens > 0:
            await self._usage_repo.record_metric(
                order_id=order_id,
                metric_type=MetricType.INPUT_TOKENS,
                value=input_tokens,
                client_id=client_id,
                context_id=context_id,
                task_id=task_id,
                metadata=metadata,
            )

        if output_tokens > 0:
            await self._usage_repo.record_metric(
                order_id=order_id,
                metric_type=MetricType.OUTPUT_TOKENS,
                value=output_tokens,
                client_id=client_id,
                context_id=context_id,
                task_id=task_id,
                metadata=metadata,
            )

        total_tokens = input_tokens + output_tokens
        if total_tokens > 0:
            await self._usage_repo.record_metric(
                order_id=order_id,
                metric_type=MetricType.TOTAL_TOKENS,
                value=total_tokens,
                client_id=client_id,
                context_id=context_id,
                task_id=task_id,
                metadata=metadata,
            )

    async def track_mcp_call(
        self,
        order_id: str,
        tool_name: str,
        client_id: str | None = None,
        context_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Track an MCP tool call.

        Args:
            order_id: The Order ID.
            tool_name: Name of the MCP tool called.
            client_id: OAuth client ID.
            context_id: Conversation context ID.
            task_id: Associated task ID.
            metadata: Additional metadata.

        Returns:
            The created usage record.
        """
        # Map tool name to specific metric type
        tool_metrics = {
            "advisor": MetricType.ADVISOR_QUERIES,
            "inventory": MetricType.INVENTORY_QUERIES,
            "vulnerability": MetricType.VULNERABILITY_QUERIES,
            "remediation": MetricType.REMEDIATION_REQUESTS,
            "planning": MetricType.PLANNING_QUERIES,
            "image_builder": MetricType.IMAGE_BUILDER_REQUESTS,
        }

        # Find matching category
        specific_metric = None
        tool_lower = tool_name.lower()
        for category, metric in tool_metrics.items():
            if category in tool_lower:
                specific_metric = metric
                break

        # Record specific tool metric if found
        if specific_metric:
            await self._usage_repo.record_metric(
                order_id=order_id,
                metric_type=specific_metric,
                client_id=client_id,
                context_id=context_id,
                task_id=task_id,
                metadata={**(metadata or {}), "tool_name": tool_name},
            )

        # Record general MCP call
        return await self._usage_repo.record_metric(
            order_id=order_id,
            metric_type=MetricType.MCP_TOOL_CALLS,
            client_id=client_id,
            context_id=context_id,
            task_id=task_id,
            metadata={**(metadata or {}), "tool_name": tool_name},
        )

    async def track_task_created(
        self,
        order_id: str,
        task_id: str,
        client_id: str | None = None,
        context_id: str | None = None,
    ) -> UsageRecord:
        """Track task creation.

        Args:
            order_id: The Order ID.
            task_id: The created task ID.
            client_id: OAuth client ID.
            context_id: Conversation context ID.

        Returns:
            The created usage record.
        """
        return await self._usage_repo.record_metric(
            order_id=order_id,
            metric_type=MetricType.TASKS_CREATED,
            client_id=client_id,
            context_id=context_id,
            task_id=task_id,
        )

    async def track_task_completed(
        self,
        order_id: str,
        task_id: str,
        client_id: str | None = None,
        context_id: str | None = None,
    ) -> UsageRecord:
        """Track task completion.

        Args:
            order_id: The Order ID.
            task_id: The completed task ID.
            client_id: OAuth client ID.
            context_id: Conversation context ID.

        Returns:
            The created usage record.
        """
        return await self._usage_repo.record_metric(
            order_id=order_id,
            metric_type=MetricType.TASKS_COMPLETED,
            client_id=client_id,
            context_id=context_id,
            task_id=task_id,
        )

    async def track_error(
        self,
        order_id: str,
        error_type: str,
        client_id: str | None = None,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> UsageRecord:
        """Track an error (non-billable, for monitoring).

        Args:
            order_id: The Order ID.
            error_type: Type of error.
            client_id: OAuth client ID.
            context_id: Conversation context ID.
            task_id: Associated task ID.

        Returns:
            The created usage record.
        """
        return await self._usage_repo.record_metric(
            order_id=order_id,
            metric_type=MetricType.ERRORS,
            client_id=client_id,
            context_id=context_id,
            task_id=task_id,
            metadata={"error_type": error_type},
        )

    async def track_rate_limited(
        self,
        order_id: str,
        client_id: str | None = None,
    ) -> UsageRecord:
        """Track a rate-limited request (non-billable).

        Args:
            order_id: The Order ID.
            client_id: OAuth client ID.

        Returns:
            The created usage record.
        """
        return await self._usage_repo.record_metric(
            order_id=order_id,
            metric_type=MetricType.RATE_LIMITED_REQUESTS,
            client_id=client_id,
        )

    async def get_usage_summary(
        self,
        order_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> UsageSummary:
        """Get usage summary for an order.

        Args:
            order_id: The Order ID.
            start_time: Start of period (default: last hour).
            end_time: End of period (default: now).

        Returns:
            Usage summary.
        """
        return await self._usage_repo.get_summary(order_id, start_time, end_time)

    async def get_billable_usage(
        self,
        order_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """Get billable usage for a reporting period.

        Args:
            order_id: The Order ID.
            start_time: Start of billing period.
            end_time: End of billing period.

        Returns:
            Dictionary of billable metrics.
        """
        return await self._usage_repo.get_billable_usage(order_id, start_time, end_time)

    async def get_all_billable_usage(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, dict[str, int]]:
        """Get billable usage for all orders in a period.

        Args:
            start_time: Start of billing period.
            end_time: End of billing period.

        Returns:
            Dictionary of order_id -> billable metrics.
        """
        order_ids = await self._usage_repo.get_orders_with_usage(start_time, end_time)
        result = {}
        for order_id in order_ids:
            result[order_id] = await self.get_billable_usage(order_id, start_time, end_time)
        return result

    async def get_current_usage(self, order_id: str) -> dict[str, int]:
        """Get current (all-time) usage counters for an order.

        Args:
            order_id: The Order ID.

        Returns:
            Dictionary of metric -> counter value.
        """
        return await self._usage_repo.get_all_counters(order_id)

    async def get_order_id_from_client_id(self, client_id: str) -> str | None:
        """Look up Order ID from client ID.

        Args:
            client_id: OAuth client ID.

        Returns:
            Order ID if found, None otherwise.
        """
        # Try DCR service first
        try:
            from insights_agent.dcr.service import get_dcr_service

            dcr_service = get_dcr_service()
            order_id = await dcr_service.get_order_id_for_client(client_id)
            if order_id:
                return order_id
        except ImportError:
            pass

        # Fall back to procurement service
        try:
            from insights_agent.marketplace.service import get_procurement_service

            procurement_service = get_procurement_service()
            return await procurement_service.get_order_id_from_client_id(client_id)
        except ImportError:
            pass

        return None


# Global service instance
_metering_service: MeteringService | None = None


def get_metering_service() -> MeteringService:
    """Get the global metering service instance.

    Returns:
        MeteringService instance.
    """
    global _metering_service
    if _metering_service is None:
        _metering_service = MeteringService()
    return _metering_service
