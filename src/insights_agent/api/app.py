"""FastAPI application for the Insights Agent."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from insights_agent.api.a2a.a2a_setup import setup_a2a_routes
from insights_agent.api.a2a.agent_card import get_agent_card_dict
from insights_agent.api.a2a.usage_plugin import get_aggregate_usage
from insights_agent.auth import oauth_router
from insights_agent.config import get_settings
from insights_agent.dcr import dcr_router
from insights_agent.marketplace import marketplace_router
from insights_agent.ratelimit import RateLimitMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    settings = get_settings()

    # Startup: Start the usage reporting scheduler
    if settings.service_control_enabled and settings.service_control_service_name:
        try:
            from insights_agent.service_control import start_reporting_scheduler

            logger.info("Starting usage reporting scheduler")
            await start_reporting_scheduler()
        except ImportError:
            logger.warning(
                "google-cloud-service-control not installed, "
                "skipping usage reporting scheduler"
            )
        except Exception as e:
            logger.error("Failed to start reporting scheduler: %s", e)

    yield

    # Shutdown: Stop the usage reporting scheduler
    if settings.service_control_enabled and settings.service_control_service_name:
        try:
            from insights_agent.service_control import stop_reporting_scheduler

            logger.info("Stopping usage reporting scheduler")
            await stop_reporting_scheduler()
        except Exception as e:
            logger.error("Failed to stop reporting scheduler: %s", e)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.agent_name,
        description=settings.agent_description,
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "agent": settings.agent_name}

    # Ready check endpoint
    @app.get("/ready")
    async def ready_check() -> dict:
        """Readiness check endpoint."""
        return {"status": "ready", "agent": settings.agent_name}

    # Set up A2A protocol routes using ADK's built-in integration
    # This provides:
    # - GET /.well-known/agent.json - AgentCard
    # - POST / - JSON-RPC 2.0 endpoint for message/send, message/stream, etc.
    # The ADK integration handles SSE streaming, task management, and
    # event conversion automatically.
    setup_a2a_routes(app)

    # Alias for agent card (some clients use agent-card.json instead of agent.json)
    @app.get("/.well-known/agent-card.json")
    async def agent_card_alias() -> dict:
        """AgentCard endpoint (alias for agent.json)."""
        return get_agent_card_dict()

    # Include OAuth 2.0 router
    # Provides: /oauth/authorize, /oauth/callback, /oauth/token, /oauth/userinfo
    app.include_router(oauth_router)

    # Include DCR router (Dynamic Client Registration)
    # Provides:
    # - POST /oauth/register - Register new OAuth client (RFC 7591)
    # - GET /oauth/register/{client_id} - Get client info
    app.include_router(dcr_router)

    # Include Marketplace Procurement router
    # Provides:
    # - POST /marketplace/pubsub - Pub/Sub push endpoint
    # - GET /marketplace/accounts/{account_id} - Get account info
    # - GET /marketplace/entitlements/{entitlement_id} - Get entitlement info
    # - GET /marketplace/orders/{order_id}/validate - Validate order for DCR
    # - GET /marketplace/accounts/{account_id}/validate - Validate account for DCR
    app.include_router(marketplace_router)

    # Usage statistics endpoint
    # Returns aggregate token and request counts tracked by UsageTrackingPlugin
    @app.get("/usage")
    async def get_usage_stats() -> dict:
        """Get aggregate usage statistics."""
        usage = get_aggregate_usage()
        return {
            "status": "ok",
            "usage": usage.to_dict(),
        }

    # Add rate limiting middleware
    app.add_middleware(RateLimitMiddleware)

    # Add CORS middleware for A2A Inspector and other browser-based clients
    # This must be added after other middleware to be processed first
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Include Service Control router (admin endpoints for usage reporting)
    # Provides:
    # - GET /service-control/status - Get scheduler status
    # - POST /service-control/report - Trigger manual report for an order
    # - POST /service-control/report/all - Trigger reports for all orders
    # - POST /service-control/retry - Retry failed reports
    if settings.service_control_enabled:
        try:
            from insights_agent.service_control import service_control_router

            app.include_router(service_control_router)
        except ImportError:
            logger.warning(
                "google-cloud-service-control not installed, "
                "skipping service control router"
            )

    return app
