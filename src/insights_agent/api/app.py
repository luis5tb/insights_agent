"""FastAPI application for the Insights Agent."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from insights_agent.api.a2a import a2a_router
from insights_agent.auth import oauth_router
from insights_agent.config import get_settings
from insights_agent.dcr import dcr_router
from insights_agent.marketplace import marketplace_router
from insights_agent.metering import MeteringMiddleware, metering_router
from insights_agent.ratelimit import RateLimitMiddleware, get_rate_limiter

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

    # Shutdown: Close rate limiter Redis connection
    try:
        rate_limiter = get_rate_limiter()
        await rate_limiter.close()
    except Exception as e:
        logger.error("Failed to close rate limiter: %s", e)


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

    # Include A2A protocol router
    # Provides:
    # - GET /.well-known/agent.json - AgentCard
    # - POST /a2a - SendMessage (JSON-RPC 2.0)
    # - POST /a2a/stream - SendStreamingMessage (SSE)
    # - GET /a2a/tasks/{task_id} - GetTask
    # - DELETE /a2a/tasks/{task_id} - CancelTask
    app.include_router(a2a_router)

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

    # Include Metering router
    # Provides:
    # - GET /metering/usage - Get usage summary for authenticated order
    # - GET /metering/usage/current - Get current (all-time) usage counters
    # - GET /metering/usage/billable - Get billable usage for billing period
    # - GET /metering/admin/usage/{order_id} - Admin: Get usage for any order
    # - GET /metering/admin/billable - Admin: Get all billable usage
    app.include_router(metering_router)

    # Add metering middleware for automatic usage tracking
    app.add_middleware(MeteringMiddleware)

    # Add rate limiting middleware
    # Note: Middleware is applied in reverse order, so rate limiting
    # is checked before metering
    app.add_middleware(RateLimitMiddleware)

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
