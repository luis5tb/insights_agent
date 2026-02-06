"""Google Cloud Marketplace Procurement integration module.

This module handles Pub/Sub events from Google Cloud Marketplace for:
- Account creation and management
- Entitlement lifecycle (creation, activation, cancellation)
- Order tracking for DCR and usage metering

Marketplace endpoints are served by the marketplace-handler service.
See insights_agent.marketplace_handler.router for the actual routing.
"""

from insights_agent.marketplace.models import (
    Account,
    AccountState,
    Entitlement,
    EntitlementState,
    ProcurementEvent,
    ProcurementEventType,
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

__all__ = [
    # Models
    "Account",
    "AccountState",
    "Entitlement",
    "EntitlementState",
    "ProcurementEvent",
    "ProcurementEventType",
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
]
