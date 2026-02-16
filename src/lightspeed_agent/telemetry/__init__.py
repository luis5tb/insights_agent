"""OpenTelemetry integration for distributed tracing."""

from lightspeed_agent.telemetry.setup import setup_telemetry, shutdown_telemetry

__all__ = ["setup_telemetry", "shutdown_telemetry"]
