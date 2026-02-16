"""Google Cloud Marketplace Procurement integration module.

This module handles:
- Pub/Sub events from Google Cloud Marketplace (account/entitlement lifecycle)
- DCR requests from Gemini Enterprise (OAuth client registration)
- Order tracking for usage metering

The marketplace handler service is run via: python -m lightspeed_agent.marketplace
"""

from lightspeed_agent.marketplace.app import create_app
from lightspeed_agent.marketplace.models import (
    Account,
    AccountState,
    Entitlement,
    EntitlementState,
    ProcurementEvent,
    ProcurementEventType,
)
from lightspeed_agent.marketplace.repository import (
    AccountRepository,
    EntitlementRepository,
    get_account_repository,
    get_entitlement_repository,
)
from lightspeed_agent.marketplace.service import (
    ProcurementService,
    get_procurement_service,
)

__all__ = [
    # App
    "create_app",
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
]
