"""Repository for storing and querying usage data."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from insights_agent.metering.metrics import (
    BILLABLE_METRICS,
    MCP_METRICS,
    TOKEN_METRICS,
    MetricType,
    UsageMetric,
    UsageRecord,
    UsageSummary,
)

logger = logging.getLogger(__name__)


class UsageRepository:
    """Repository for usage records.

    In production, this should be backed by a database (PostgreSQL, BigQuery, etc.).
    This implementation uses in-memory storage for development.
    """

    def __init__(self) -> None:
        """Initialize the usage repository."""
        # Records indexed by order_id -> list of records
        self._records: dict[str, list[UsageRecord]] = defaultdict(list)
        # Quick lookup by record ID
        self._records_by_id: dict[str, UsageRecord] = {}
        # Aggregated counters for quick access
        self._counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    async def record(self, record: UsageRecord) -> UsageRecord:
        """Record a usage metric.

        Args:
            record: The usage record to store.

        Returns:
            The stored record with generated ID.
        """
        if not record.id:
            record.id = str(uuid4())

        self._records[record.order_id].append(record)
        self._records_by_id[record.id] = record

        # Update counters
        self._counters[record.order_id][record.metric.metric_type.value] += record.metric.value

        logger.debug(
            "Recorded usage: order=%s, metric=%s, value=%d",
            record.order_id,
            record.metric.metric_type.value,
            record.metric.value,
        )

        return record

    async def record_metric(
        self,
        order_id: str,
        metric_type: MetricType,
        value: int = 1,
        client_id: str | None = None,
        context_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record a usage metric (convenience method).

        Args:
            order_id: The Order ID to record against.
            metric_type: Type of metric.
            value: Metric value (default: 1).
            client_id: OAuth client ID.
            context_id: Conversation context ID.
            task_id: Associated task ID.
            metadata: Additional metadata.

        Returns:
            The created usage record.
        """
        record = UsageRecord(
            id=str(uuid4()),
            order_id=order_id,
            client_id=client_id,
            metric=UsageMetric(
                metric_type=metric_type,
                value=value,
                metadata=metadata or {},
            ),
            context_id=context_id,
            task_id=task_id,
        )

        return await self.record(record)

    async def get_records(
        self,
        order_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        metric_type: MetricType | None = None,
        limit: int = 1000,
    ) -> list[UsageRecord]:
        """Get usage records for an order.

        Args:
            order_id: The Order ID.
            start_time: Filter by start time.
            end_time: Filter by end time.
            metric_type: Filter by metric type.
            limit: Maximum records to return.

        Returns:
            List of matching usage records.
        """
        records = self._records.get(order_id, [])

        # Apply filters
        if start_time:
            records = [r for r in records if r.created_at >= start_time]
        if end_time:
            records = [r for r in records if r.created_at <= end_time]
        if metric_type:
            records = [r for r in records if r.metric.metric_type == metric_type]

        # Sort by timestamp (newest first) and limit
        records = sorted(records, key=lambda r: r.created_at, reverse=True)[:limit]

        return records

    async def get_summary(
        self,
        order_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> UsageSummary:
        """Get aggregated usage summary for an order.

        Args:
            order_id: The Order ID.
            start_time: Start of reporting period.
            end_time: End of reporting period.

        Returns:
            Aggregated usage summary.
        """
        now = datetime.utcnow()
        start = start_time or (now - timedelta(hours=1))
        end = end_time or now

        records = await self.get_records(order_id, start, end)

        # Aggregate metrics
        metrics: dict[str, int] = defaultdict(int)
        for record in records:
            metrics[record.metric.metric_type.value] += record.metric.value

        # Calculate totals
        total_api_calls = sum(
            metrics.get(m.value, 0)
            for m in [
                MetricType.API_CALLS,
                MetricType.SEND_MESSAGE_REQUESTS,
                MetricType.STREAMING_REQUESTS,
            ]
        )

        total_tokens = sum(
            metrics.get(m.value, 0) for m in TOKEN_METRICS
        )

        total_mcp_calls = sum(
            metrics.get(m.value, 0) for m in MCP_METRICS
        )

        return UsageSummary(
            order_id=order_id,
            period_start=start,
            period_end=end,
            metrics=dict(metrics),
            total_api_calls=total_api_calls,
            total_tokens=total_tokens,
            total_mcp_calls=total_mcp_calls,
        )

    async def get_counter(
        self,
        order_id: str,
        metric_type: MetricType,
    ) -> int:
        """Get current counter value for a metric.

        This is a quick lookup without filtering by time.

        Args:
            order_id: The Order ID.
            metric_type: The metric type.

        Returns:
            Current counter value.
        """
        return self._counters[order_id][metric_type.value]

    async def get_all_counters(self, order_id: str) -> dict[str, int]:
        """Get all counter values for an order.

        Args:
            order_id: The Order ID.

        Returns:
            Dictionary of metric type -> counter value.
        """
        return dict(self._counters[order_id])

    async def get_billable_usage(
        self,
        order_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """Get billable usage for reporting period.

        Args:
            order_id: The Order ID.
            start_time: Start of billing period.
            end_time: End of billing period.

        Returns:
            Dictionary of billable metric -> usage value.
        """
        records = await self.get_records(order_id, start_time, end_time)

        billable: dict[str, int] = {}
        for record in records:
            if record.metric.metric_type in BILLABLE_METRICS:
                key = record.metric.metric_type.value
                billable[key] = billable.get(key, 0) + record.metric.value

        return billable

    async def get_orders_with_usage(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[str]:
        """Get all order IDs with usage in the given period.

        Args:
            start_time: Start of period.
            end_time: End of period.

        Returns:
            List of order IDs.
        """
        order_ids = []
        for order_id, records in self._records.items():
            # Check if any records fall within the period
            if start_time or end_time:
                matching = False
                for record in records:
                    if start_time and record.created_at < start_time:
                        continue
                    if end_time and record.created_at > end_time:
                        continue
                    matching = True
                    break
                if matching:
                    order_ids.append(order_id)
            else:
                if records:
                    order_ids.append(order_id)

        return order_ids

    async def clear_old_records(self, before: datetime) -> int:
        """Clear records older than the given timestamp.

        Args:
            before: Clear records before this time.

        Returns:
            Number of records cleared.
        """
        cleared = 0
        for order_id in list(self._records.keys()):
            original_count = len(self._records[order_id])
            self._records[order_id] = [
                r for r in self._records[order_id] if r.created_at >= before
            ]
            cleared += original_count - len(self._records[order_id])

            # Remove from ID index
            for record_id in list(self._records_by_id.keys()):
                record = self._records_by_id[record_id]
                if record.created_at < before:
                    del self._records_by_id[record_id]

        logger.info("Cleared %d old usage records", cleared)
        return cleared


# Global repository instance
_usage_repo: UsageRepository | None = None


def get_usage_repository() -> UsageRepository:
    """Get the global usage repository instance.

    Returns:
        UsageRepository instance.
    """
    global _usage_repo
    if _usage_repo is None:
        _usage_repo = UsageRepository()
    return _usage_repo
