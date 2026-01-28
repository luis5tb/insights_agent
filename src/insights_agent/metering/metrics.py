"""Metrics definitions for usage metering."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MetricType(str, Enum):
    """Types of billable metrics."""

    # API call metrics
    API_CALLS = "api_calls"
    SEND_MESSAGE_REQUESTS = "send_message_requests"
    STREAMING_REQUESTS = "streaming_requests"

    # Token usage metrics
    INPUT_TOKENS = "input_tokens"
    OUTPUT_TOKENS = "output_tokens"
    TOTAL_TOKENS = "total_tokens"

    # MCP tool metrics
    MCP_TOOL_CALLS = "mcp_tool_calls"
    ADVISOR_QUERIES = "advisor_queries"
    INVENTORY_QUERIES = "inventory_queries"
    VULNERABILITY_QUERIES = "vulnerability_queries"
    REMEDIATION_REQUESTS = "remediation_requests"
    PLANNING_QUERIES = "planning_queries"
    IMAGE_BUILDER_REQUESTS = "image_builder_requests"

    # Task metrics
    TASKS_CREATED = "tasks_created"
    TASKS_COMPLETED = "tasks_completed"

    # Error metrics (non-billable, for monitoring)
    ERRORS = "errors"
    RATE_LIMITED_REQUESTS = "rate_limited_requests"


class UsageMetric(BaseModel):
    """A single usage metric data point."""

    metric_type: MetricType = Field(..., description="Type of metric")
    value: int = Field(default=1, description="Metric value (count or quantity)")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the metric was recorded",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metric metadata",
    )


class UsageRecord(BaseModel):
    """A usage record for a specific order."""

    id: str = Field(..., description="Unique record ID")
    order_id: str = Field(..., description="Associated Order ID")
    client_id: str | None = Field(None, description="OAuth client ID")
    metric: UsageMetric = Field(..., description="The usage metric")
    context_id: str | None = Field(None, description="Conversation context ID")
    task_id: str | None = Field(None, description="Associated task ID")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Record creation timestamp",
    )


class UsageSummary(BaseModel):
    """Aggregated usage summary for an order."""

    order_id: str = Field(..., description="Order ID")
    period_start: datetime = Field(..., description="Start of reporting period")
    period_end: datetime = Field(..., description="End of reporting period")
    metrics: dict[str, int] = Field(
        default_factory=dict,
        description="Aggregated metric values by type",
    )
    total_api_calls: int = Field(default=0, description="Total API calls")
    total_tokens: int = Field(default=0, description="Total token usage")
    total_mcp_calls: int = Field(default=0, description="Total MCP tool calls")


class BillingPeriod(BaseModel):
    """A billing period for usage reporting."""

    start: datetime = Field(..., description="Period start")
    end: datetime = Field(..., description="Period end")
    reported: bool = Field(default=False, description="Whether reported to Google")
    reported_at: datetime | None = Field(None, description="When reported")


# Metric categories for aggregation
BILLABLE_METRICS = [
    MetricType.API_CALLS,
    MetricType.SEND_MESSAGE_REQUESTS,
    MetricType.STREAMING_REQUESTS,
    MetricType.INPUT_TOKENS,
    MetricType.OUTPUT_TOKENS,
    MetricType.TOTAL_TOKENS,
    MetricType.MCP_TOOL_CALLS,
]

TOKEN_METRICS = [
    MetricType.INPUT_TOKENS,
    MetricType.OUTPUT_TOKENS,
    MetricType.TOTAL_TOKENS,
]

MCP_METRICS = [
    MetricType.MCP_TOOL_CALLS,
    MetricType.ADVISOR_QUERIES,
    MetricType.INVENTORY_QUERIES,
    MetricType.VULNERABILITY_QUERIES,
    MetricType.REMEDIATION_REQUESTS,
    MetricType.PLANNING_QUERIES,
    MetricType.IMAGE_BUILDER_REQUESTS,
]
