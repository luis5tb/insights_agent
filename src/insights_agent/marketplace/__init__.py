"""Google Cloud Marketplace Procurement integration module.

This module handles Pub/Sub events from Google Cloud Marketplace for:
- Account creation and management
- Entitlement lifecycle (creation, activation, cancellation)
- Order tracking for DCR and usage metering
"""

from insights_agent.marketplace.models import (
    Account,
    AccountState,
    Entitlement,
    EntitlementState,
    ProcurementEvent,
    ProcurementEventType,
    PubSubMessage,
)
from insights_agent.marketplace.repository import (
    AccountRepository,
    EntitlementRepository,
    get_account_repository,
    get_entitlement_repository,
)
from insights_agent.marketplace.service import (
    ProcurementService,
    get_procurement_service,
)
from insights_agent.marketplace.pubsub_handler import (
    PubSubHandler,
    get_pubsub_handler,
)
from insights_agent.marketplace.router import router as marketplace_router

__all__ = [
    # Models
    "Account",
    "AccountState",
    "Entitlement",
    "EntitlementState",
    "ProcurementEvent",
    "ProcurementEventType",
    "PubSubMessage",
    # Repository
    "AccountRepository",
    "EntitlementRepository",
    "get_account_repository",
    "get_entitlement_repository",
    # Service
    "ProcurementService",
    "get_procurement_service",
    # Pub/Sub Handler
    "PubSubHandler",
    "get_pubsub_handler",
    # Router
    "marketplace_router",
]
