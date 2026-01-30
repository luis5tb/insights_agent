"""Main entry point for the Insights Agent."""

import logging
import sys

import uvicorn
from dotenv import load_dotenv

from insights_agent.config import get_settings


def setup_logging() -> None:
    """Configure application logging."""
    settings = get_settings()

    log_format = (
        '{"time": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "message": "%(message)s"}'
        if settings.log_format == "json"
        else "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> None:
    """Run the Insights Agent server."""
    # Load environment variables from .env file
    load_dotenv()

    # Set up logging
    setup_logging()

    settings = get_settings()
    logger = logging.getLogger(__name__)

    # Initialize OpenTelemetry tracing (must be done before creating app)
    from insights_agent.telemetry import setup_telemetry, shutdown_telemetry

    setup_telemetry()

    logger.info(
        "Starting Insights Agent",
        extra={
            "agent_name": settings.agent_name,
            "model": settings.gemini_model,
            "host": settings.agent_host,
            "port": settings.agent_port,
            "otel_enabled": settings.otel_enabled,
        },
    )

    # Import app here to ensure environment is configured
    from insights_agent.api.app import create_app

    app = create_app()

    try:
        uvicorn.run(
            app,
            host=settings.agent_host,
            port=settings.agent_port,
            log_level=settings.log_level.lower(),
        )
    finally:
        # Ensure telemetry is properly shut down
        shutdown_telemetry()


if __name__ == "__main__":
    main()
