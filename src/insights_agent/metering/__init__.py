"""Usage metering and tracking module.

This module tracks billable metrics for the agent including:
- API calls/queries per order
- Token usage (input/output)
- MCP tool invocations
"""

from insights_agent.metering.metrics import (
    MetricType,
    UsageMetric,
    UsageRecord,
    UsageSummary,
)
from insights_agent.metering.repository import (
    UsageRepository,
    get_usage_repository,
)
from insights_agent.metering.service import (
    MeteringService,
    get_metering_service,
)
from insights_agent.metering.middleware import (
    MeteringMiddleware,
    get_order_id_from_request,
)
from insights_agent.metering.router import router as metering_router

__all__ = [
    # Metrics
    "MetricType",
    "UsageMetric",
    "UsageRecord",
    "UsageSummary",
    # Repository
    "UsageRepository",
    "get_usage_repository",
    # Service
    "MeteringService",
    "get_metering_service",
    # Middleware
    "MeteringMiddleware",
    "get_order_id_from_request",
    # Router
    "metering_router",
]
