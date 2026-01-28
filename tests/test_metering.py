"""Tests for usage metering module."""

import asyncio
from datetime import datetime, timedelta

import pytest

from insights_agent.metering.metrics import (
    BILLABLE_METRICS,
    MetricType,
    UsageMetric,
    UsageRecord,
    UsageSummary,
)
from insights_agent.metering.repository import UsageRepository
from insights_agent.metering.service import MeteringService


class TestMetricModels:
    """Tests for metric data models."""

    def test_metric_type_enum(self):
        """Test MetricType enum values."""
        assert MetricType.API_CALLS.value == "api_calls"
        assert MetricType.INPUT_TOKENS.value == "input_tokens"
        assert MetricType.MCP_TOOL_CALLS.value == "mcp_tool_calls"

    def test_usage_metric_defaults(self):
        """Test UsageMetric default values."""
        metric = UsageMetric(metric_type=MetricType.API_CALLS)

        assert metric.value == 1
        assert metric.metadata == {}
        assert metric.timestamp is not None

    def test_usage_metric_with_value(self):
        """Test UsageMetric with custom value."""
        metric = UsageMetric(
            metric_type=MetricType.INPUT_TOKENS,
            value=1500,
            metadata={"model": "gemini-2.5-flash"},
        )

        assert metric.value == 1500
        assert metric.metadata["model"] == "gemini-2.5-flash"

    def test_usage_record(self):
        """Test UsageRecord model."""
        record = UsageRecord(
            id="record-123",
            order_id="order-456",
            client_id="client-789",
            metric=UsageMetric(metric_type=MetricType.API_CALLS),
            context_id="context-abc",
            task_id="task-def",
        )

        assert record.id == "record-123"
        assert record.order_id == "order-456"
        assert record.client_id == "client-789"
        assert record.context_id == "context-abc"
        assert record.created_at is not None

    def test_usage_summary(self):
        """Test UsageSummary model."""
        now = datetime.utcnow()
        summary = UsageSummary(
            order_id="order-123",
            period_start=now - timedelta(hours=1),
            period_end=now,
            metrics={"api_calls": 100, "input_tokens": 5000},
            total_api_calls=100,
            total_tokens=5000,
            total_mcp_calls=10,
        )

        assert summary.order_id == "order-123"
        assert summary.total_api_calls == 100
        assert summary.metrics["input_tokens"] == 5000

    def test_billable_metrics_list(self):
        """Test that billable metrics are defined."""
        assert MetricType.API_CALLS in BILLABLE_METRICS
        assert MetricType.INPUT_TOKENS in BILLABLE_METRICS
        assert MetricType.OUTPUT_TOKENS in BILLABLE_METRICS
        # Non-billable metrics should not be in the list
        assert MetricType.ERRORS not in BILLABLE_METRICS
        assert MetricType.RATE_LIMITED_REQUESTS not in BILLABLE_METRICS


class TestUsageRepository:
    """Tests for UsageRepository."""

    @pytest.fixture
    def repo(self):
        """Create a fresh repository."""
        return UsageRepository()

    @pytest.mark.asyncio
    async def test_record_metric(self, repo):
        """Test recording a metric."""
        record = await repo.record_metric(
            order_id="order-123",
            metric_type=MetricType.API_CALLS,
        )

        assert record.id is not None
        assert record.order_id == "order-123"
        assert record.metric.metric_type == MetricType.API_CALLS
        assert record.metric.value == 1

    @pytest.mark.asyncio
    async def test_record_metric_with_value(self, repo):
        """Test recording a metric with custom value."""
        record = await repo.record_metric(
            order_id="order-123",
            metric_type=MetricType.INPUT_TOKENS,
            value=1500,
        )

        assert record.metric.value == 1500

    @pytest.mark.asyncio
    async def test_get_records(self, repo):
        """Test getting records for an order."""
        # Record several metrics
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(order_id="order-456", metric_type=MetricType.API_CALLS)

        records = await repo.get_records("order-123")

        assert len(records) == 2
        assert all(r.order_id == "order-123" for r in records)

    @pytest.mark.asyncio
    async def test_get_records_with_filter(self, repo):
        """Test getting records with metric type filter."""
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(
            order_id="order-123", metric_type=MetricType.INPUT_TOKENS, value=100
        )

        records = await repo.get_records(
            "order-123", metric_type=MetricType.INPUT_TOKENS
        )

        assert len(records) == 1
        assert records[0].metric.metric_type == MetricType.INPUT_TOKENS

    @pytest.mark.asyncio
    async def test_get_counter(self, repo):
        """Test getting counter value."""
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)

        counter = await repo.get_counter("order-123", MetricType.API_CALLS)

        assert counter == 2

    @pytest.mark.asyncio
    async def test_get_all_counters(self, repo):
        """Test getting all counters for an order."""
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(
            order_id="order-123", metric_type=MetricType.INPUT_TOKENS, value=500
        )

        counters = await repo.get_all_counters("order-123")

        assert counters["api_calls"] == 1
        assert counters["input_tokens"] == 500

    @pytest.mark.asyncio
    async def test_get_summary(self, repo):
        """Test getting usage summary."""
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(
            order_id="order-123", metric_type=MetricType.INPUT_TOKENS, value=1000
        )
        await repo.record_metric(
            order_id="order-123", metric_type=MetricType.OUTPUT_TOKENS, value=500
        )

        summary = await repo.get_summary("order-123")

        assert summary.order_id == "order-123"
        assert summary.metrics["api_calls"] == 1
        assert summary.metrics["input_tokens"] == 1000
        assert summary.metrics["output_tokens"] == 500

    @pytest.mark.asyncio
    async def test_get_billable_usage(self, repo):
        """Test getting billable usage."""
        now = datetime.utcnow()
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)

        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(
            order_id="order-123", metric_type=MetricType.INPUT_TOKENS, value=1000
        )
        # Non-billable metric
        await repo.record_metric(order_id="order-123", metric_type=MetricType.ERRORS)

        billable = await repo.get_billable_usage("order-123", start, end)

        assert "api_calls" in billable
        assert "input_tokens" in billable
        assert "errors" not in billable

    @pytest.mark.asyncio
    async def test_get_orders_with_usage(self, repo):
        """Test getting orders with usage."""
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)
        await repo.record_metric(order_id="order-456", metric_type=MetricType.API_CALLS)

        orders = await repo.get_orders_with_usage()

        assert "order-123" in orders
        assert "order-456" in orders

    @pytest.mark.asyncio
    async def test_clear_old_records(self, repo):
        """Test clearing old records."""
        # Create a record
        await repo.record_metric(order_id="order-123", metric_type=MetricType.API_CALLS)

        # Clear records older than future date (should clear all)
        cleared = await repo.clear_old_records(datetime.utcnow() + timedelta(days=1))

        assert cleared == 1

        records = await repo.get_records("order-123")
        assert len(records) == 0


class TestMeteringService:
    """Tests for MeteringService."""

    @pytest.fixture
    def service(self):
        """Create a fresh metering service."""
        repo = UsageRepository()
        return MeteringService(usage_repo=repo)

    @pytest.mark.asyncio
    async def test_track_api_call(self, service):
        """Test tracking an API call."""
        record = await service.track_api_call(
            order_id="order-123",
            client_id="client-456",
            streaming=False,
        )

        assert record.order_id == "order-123"
        assert record.client_id == "client-456"
        assert record.metric.metric_type == MetricType.API_CALLS

    @pytest.mark.asyncio
    async def test_track_streaming_api_call(self, service):
        """Test tracking a streaming API call."""
        record = await service.track_api_call(
            order_id="order-123",
            streaming=True,
        )

        # Should track both streaming and general API call
        usage = await service.get_current_usage("order-123")

        assert usage.get("streaming_requests", 0) == 1
        assert usage.get("api_calls", 0) == 1

    @pytest.mark.asyncio
    async def test_track_token_usage(self, service):
        """Test tracking token usage."""
        await service.track_token_usage(
            order_id="order-123",
            input_tokens=1000,
            output_tokens=500,
        )

        usage = await service.get_current_usage("order-123")

        assert usage["input_tokens"] == 1000
        assert usage["output_tokens"] == 500
        assert usage["total_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_track_token_usage_zero_values(self, service):
        """Test that zero token values are not recorded."""
        await service.track_token_usage(
            order_id="order-123",
            input_tokens=0,
            output_tokens=0,
        )

        usage = await service.get_current_usage("order-123")

        assert usage.get("input_tokens", 0) == 0
        assert usage.get("output_tokens", 0) == 0

    @pytest.mark.asyncio
    async def test_track_mcp_call(self, service):
        """Test tracking an MCP tool call."""
        record = await service.track_mcp_call(
            order_id="order-123",
            tool_name="advisor_get_recommendations",
        )

        assert record.metric.metric_type == MetricType.MCP_TOOL_CALLS

        usage = await service.get_current_usage("order-123")

        # Should track both specific and general MCP call
        assert usage.get("advisor_queries", 0) == 1
        assert usage.get("mcp_tool_calls", 0) == 1

    @pytest.mark.asyncio
    async def test_track_mcp_call_unknown_tool(self, service):
        """Test tracking an unknown MCP tool call."""
        await service.track_mcp_call(
            order_id="order-123",
            tool_name="unknown_tool",
        )

        usage = await service.get_current_usage("order-123")

        # Should only track general MCP call
        assert usage.get("mcp_tool_calls", 0) == 1
        assert usage.get("advisor_queries", 0) == 0

    @pytest.mark.asyncio
    async def test_track_task_lifecycle(self, service):
        """Test tracking task creation and completion."""
        await service.track_task_created(
            order_id="order-123",
            task_id="task-456",
        )
        await service.track_task_completed(
            order_id="order-123",
            task_id="task-456",
        )

        usage = await service.get_current_usage("order-123")

        assert usage["tasks_created"] == 1
        assert usage["tasks_completed"] == 1

    @pytest.mark.asyncio
    async def test_track_error(self, service):
        """Test tracking an error."""
        record = await service.track_error(
            order_id="order-123",
            error_type="validation_error",
        )

        assert record.metric.metric_type == MetricType.ERRORS
        assert record.metric.metadata["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_track_rate_limited(self, service):
        """Test tracking a rate-limited request."""
        record = await service.track_rate_limited(
            order_id="order-123",
            client_id="client-456",
        )

        assert record.metric.metric_type == MetricType.RATE_LIMITED_REQUESTS

    @pytest.mark.asyncio
    async def test_get_usage_summary(self, service):
        """Test getting usage summary."""
        await service.track_api_call(order_id="order-123")
        await service.track_token_usage(
            order_id="order-123", input_tokens=1000, output_tokens=500
        )

        summary = await service.get_usage_summary("order-123")

        assert summary.order_id == "order-123"
        assert summary.total_tokens > 0

    @pytest.mark.asyncio
    async def test_get_billable_usage(self, service):
        """Test getting billable usage."""
        now = datetime.utcnow()

        await service.track_api_call(order_id="order-123")
        await service.track_error(order_id="order-123", error_type="test")

        billable = await service.get_billable_usage(
            order_id="order-123",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert "api_calls" in billable
        assert "errors" not in billable  # Errors are non-billable

    @pytest.mark.asyncio
    async def test_get_all_billable_usage(self, service):
        """Test getting all billable usage."""
        now = datetime.utcnow()

        await service.track_api_call(order_id="order-123")
        await service.track_api_call(order_id="order-456")

        all_usage = await service.get_all_billable_usage(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert "order-123" in all_usage
        assert "order-456" in all_usage
