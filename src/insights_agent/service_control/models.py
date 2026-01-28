"""Data models for Google Cloud Service Control API."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CheckErrorCode(str, Enum):
    """Error codes from Service Control check response."""

    # Service not activated for the consumer
    SERVICE_NOT_ACTIVATED = "SERVICE_NOT_ACTIVATED"
    # Billing is disabled for the consumer
    BILLING_DISABLED = "BILLING_DISABLED"
    # Consumer project has been deleted
    PROJECT_DELETED = "PROJECT_DELETED"
    # Consumer project is marked for deletion
    PROJECT_INVALID = "PROJECT_INVALID"
    # IP address blocked
    IP_ADDRESS_BLOCKED = "IP_ADDRESS_BLOCKED"
    # Referer blocked
    REFERER_BLOCKED = "REFERER_BLOCKED"
    # Client app blocked
    CLIENT_APP_BLOCKED = "CLIENT_APP_BLOCKED"
    # API key invalid
    API_KEY_INVALID = "API_KEY_INVALID"
    # API key expired
    API_KEY_EXPIRED = "API_KEY_EXPIRED"
    # API key not found
    API_KEY_NOT_FOUND = "API_KEY_NOT_FOUND"
    # Namespace lookup failed
    NAMESPACE_LOOKUP_UNAVAILABLE = "NAMESPACE_LOOKUP_UNAVAILABLE"
    # Service status unavailable
    SERVICE_STATUS_UNAVAILABLE = "SERVICE_STATUS_UNAVAILABLE"
    # Billing status unavailable
    BILLING_STATUS_UNAVAILABLE = "BILLING_STATUS_UNAVAILABLE"


class CheckError(BaseModel):
    """Error from Service Control check response."""

    code: CheckErrorCode = Field(..., description="Error code")
    detail: str = Field(default="", description="Error detail message")


class MetricValue(BaseModel):
    """A metric value for reporting."""

    int64_value: int | None = Field(None, alias="int64Value", description="Integer value")
    double_value: float | None = Field(None, alias="doubleValue", description="Double value")
    string_value: str | None = Field(None, alias="stringValue", description="String value")
    bool_value: bool | None = Field(None, alias="boolValue", description="Boolean value")

    class Config:
        populate_by_name = True


class MetricValueSet(BaseModel):
    """A set of metric values for a single metric."""

    metric_name: str = Field(..., alias="metricName", description="Metric name")
    metric_values: list[MetricValue] = Field(
        ..., alias="metricValues", description="Metric values"
    )

    class Config:
        populate_by_name = True


class Operation(BaseModel):
    """An operation for Service Control check/report.

    Represents a single usage event or aggregated usage for reporting.
    """

    operation_id: str = Field(..., alias="operationId", description="Unique operation ID")
    operation_name: str | None = Field(
        None, alias="operationName", description="Operation name (e.g., API method)"
    )
    consumer_id: str = Field(..., alias="consumerId", description="Consumer ID (usageReportingId)")
    start_time: datetime = Field(..., alias="startTime", description="Start of reporting period")
    end_time: datetime | None = Field(None, alias="endTime", description="End of reporting period")
    labels: dict[str, str] = Field(default_factory=dict, description="Operation labels")
    metric_value_sets: list[MetricValueSet] = Field(
        default_factory=list, alias="metricValueSets", description="Metric values"
    )
    user_labels: dict[str, str] = Field(
        default_factory=dict, alias="userLabels", description="User-defined labels"
    )

    class Config:
        populate_by_name = True


class CheckRequest(BaseModel):
    """Request for services.check API."""

    operation: Operation = Field(..., description="Operation to check")


class CheckResponse(BaseModel):
    """Response from services.check API."""

    operation_id: str = Field(..., alias="operationId", description="Operation ID")
    check_errors: list[CheckError] = Field(
        default_factory=list, alias="checkErrors", description="Check errors"
    )

    class Config:
        populate_by_name = True

    @property
    def is_valid(self) -> bool:
        """Check if the response indicates a valid consumer."""
        return len(self.check_errors) == 0

    @property
    def should_block_service(self) -> bool:
        """Check if service should be blocked based on errors."""
        blocking_codes = {
            CheckErrorCode.SERVICE_NOT_ACTIVATED,
            CheckErrorCode.BILLING_DISABLED,
            CheckErrorCode.PROJECT_DELETED,
        }
        return any(e.code in blocking_codes for e in self.check_errors)


class ReportRequest(BaseModel):
    """Request for services.report API."""

    operations: list[Operation] = Field(..., description="Operations to report")


class ReportResponse(BaseModel):
    """Response from services.report API."""

    report_errors: list[dict[str, Any]] = Field(
        default_factory=list, alias="reportErrors", description="Report errors"
    )
    service_config_id: str | None = Field(
        None, alias="serviceConfigId", description="Service config ID"
    )
    service_rollout_id: str | None = Field(
        None, alias="serviceRolloutId", description="Service rollout ID"
    )

    class Config:
        populate_by_name = True

    @property
    def is_success(self) -> bool:
        """Check if report was successful."""
        return len(self.report_errors) == 0


class UsageReport(BaseModel):
    """A usage report to be sent to Service Control."""

    order_id: str = Field(..., description="Order ID (entitlement ID)")
    consumer_id: str = Field(..., description="Consumer ID (usageReportingId)")
    start_time: datetime = Field(..., description="Start of reporting period")
    end_time: datetime = Field(..., description="End of reporting period")
    metrics: dict[str, int] = Field(default_factory=dict, description="Metric name -> value")
    reported: bool = Field(default=False, description="Whether successfully reported")
    reported_at: datetime | None = Field(None, description="When reported")
    error_message: str | None = Field(None, description="Error if report failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")


class ReportingPeriod(BaseModel):
    """A reporting period for usage aggregation."""

    start_time: datetime = Field(..., description="Period start")
    end_time: datetime = Field(..., description="Period end")


class ServiceConfig(BaseModel):
    """Configuration for the service being controlled."""

    service_name: str = Field(..., description="Service name (e.g., myservice.gcpmarketplace.example.com)")
    metric_prefix: str = Field(..., description="Metric prefix for the service")
    enabled: bool = Field(default=True, description="Whether reporting is enabled")
