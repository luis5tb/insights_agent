"""Marketplace Handler Service.

A separate service that handles:
1. Pub/Sub events from Google Cloud Marketplace (async provisioning)
2. DCR requests from Gemini Enterprise (sync client registration)

This service must be always running to receive procurement events,
even before any agent instances are deployed.

Deployment Flow:
1. Customer purchases from Google Marketplace
2. Pub/Sub event → This service (approves account/entitlement)
3. User configures agent in Gemini Enterprise
4. Gemini sends DCR request → This service (creates OAuth client)
5. User interacts with agent → Agent Service (uses OAuth tokens)
"""

from insights_agent.marketplace_handler.app import create_app

__all__ = ["create_app"]
