"""Application settings and configuration management."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Google AI / Gemini Configuration
    google_genai_use_vertexai: bool = Field(
        default=False,
        description="Use Vertex AI instead of Google AI Studio",
    )
    google_api_key: str | None = Field(
        default=None,
        description="Google AI Studio API key",
    )
    google_cloud_project: str | None = Field(
        default=None,
        description="Google Cloud project ID for Vertex AI",
    )
    google_cloud_location: str = Field(
        default="us-central1",
        description="Google Cloud location for Vertex AI",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model to use",
    )

    # Red Hat SSO Configuration
    red_hat_sso_issuer: str = Field(
        default="https://sso.redhat.com/auth/realms/redhat-external",
        description="Red Hat SSO issuer URL",
    )
    red_hat_sso_client_id: str = Field(
        default="",
        description="OAuth client ID for Red Hat SSO",
    )
    red_hat_sso_client_secret: str = Field(
        default="",
        description="OAuth client secret for Red Hat SSO",
    )
    red_hat_sso_redirect_uri: str = Field(
        default="http://localhost:8000/oauth/callback",
        description="OAuth redirect URI",
    )
    red_hat_sso_jwks_uri: str = Field(
        default="https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs",
        description="JWKS endpoint for token validation",
    )

    # Red Hat Insights MCP Configuration
    lightspeed_client_id: str = Field(
        default="",
        description="Lightspeed service account client ID",
    )
    lightspeed_client_secret: str = Field(
        default="",
        description="Lightspeed service account client secret",
    )
    mcp_transport_mode: Literal["stdio", "http", "sse"] = Field(
        default="stdio",
        description="MCP server transport mode",
    )
    mcp_server_url: str = Field(
        default="http://localhost:8080",
        description="MCP server URL for http/sse modes",
    )
    mcp_read_only: bool = Field(
        default=True,
        description="Enable read-only mode for MCP tools",
    )

    # Agent Configuration
    agent_provider_url: str = Field(
        default="https://localhost:8000",
        description="Agent provider URL for AgentCard",
    )
    agent_name: str = Field(
        default="insights_agent",
        description="Agent name (must be a valid Python identifier)",
    )
    agent_description: str = Field(
        default="Red Hat Insights Agent for infrastructure management",
        description="Agent description",
    )
    agent_host: str = Field(
        default="0.0.0.0",
        description="Server host",
    )
    agent_port: int = Field(
        default=8000,
        description="Server port",
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite+aiosqlite:///./insights_agent.db",
        description="Database connection URL",
    )

    # Google Cloud Service Control
    service_control_service_name: str = Field(
        default="",
        description="Service name for Google Cloud Service Control (e.g., myservice.gcpmarketplace.example.com)",
    )
    service_control_enabled: bool = Field(
        default=True,
        description="Enable usage reporting to Google Cloud Service Control",
    )
    service_control_retry_max_attempts: int = Field(
        default=3,
        description="Maximum retry attempts for failed usage reports",
    )
    service_control_retry_delay_seconds: int = Field(
        default=300,
        description="Delay between retry attempts for failed reports",
    )

    # Rate Limiting (in-memory, no Redis required)
    rate_limit_requests_per_minute: int = Field(
        default=60,
        description="Global requests per minute limit",
    )
    rate_limit_requests_per_hour: int = Field(
        default=1000,
        description="Global requests per hour limit",
    )

    # Usage Reporting
    usage_report_interval_seconds: int = Field(
        default=3600,
        description="Usage report interval in seconds",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log format",
    )

    # Development Settings
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )
    skip_jwt_validation: bool = Field(
        default=False,
        description="Skip JWT validation (development only)",
    )

    # OpenTelemetry Configuration
    otel_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing",
    )
    otel_service_name: str = Field(
        default="insights_agent",
        description="Service name for OpenTelemetry traces",
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP exporter endpoint (gRPC)",
    )
    otel_exporter_otlp_http_endpoint: str = Field(
        default="http://localhost:4318",
        description="OTLP exporter endpoint (HTTP)",
    )
    otel_exporter_type: Literal["otlp", "otlp-http", "jaeger", "zipkin", "console"] = Field(
        default="otlp",
        description="Telemetry exporter type",
    )
    otel_traces_sampler: Literal["always_on", "always_off", "traceidratio", "parentbased_always_on", "parentbased_always_off", "parentbased_traceidratio"] = Field(
        default="always_on",
        description="Trace sampling strategy",
    )
    otel_traces_sampler_arg: float = Field(
        default=1.0,
        description="Sampler argument (e.g., ratio for traceidratio)",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
