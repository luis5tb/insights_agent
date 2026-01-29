"""Header provider for MCP toolset to inject per-user credentials."""

import logging
from typing import TYPE_CHECKING

from insights_agent.config import get_settings

if TYPE_CHECKING:
    from google.adk.agents.readonly_context import ReadonlyContext

logger = logging.getLogger(__name__)

# Session state keys for storing user's lightspeed credentials
LIGHTSPEED_CLIENT_ID_KEY = "lightspeed_client_id"
LIGHTSPEED_CLIENT_SECRET_KEY = "lightspeed_client_secret"


def create_mcp_header_provider():
    """Create a header provider function for McpToolset.

    The returned function extracts the user's lightspeed credentials from the
    session state and returns appropriate headers for the MCP server. If no
    credentials are found in session state, it falls back to agent-level
    credentials from environment variables.

    Returns:
        A callable that takes ReadonlyContext and returns headers dict.
    """

    def header_provider(context: "ReadonlyContext") -> dict[str, str]:
        """Provide headers for MCP requests based on session context.

        Credential resolution order:
        1. Session state (from user's JWT claims)
        2. Environment variables (agent-level fallback)

        Args:
            context: The readonly context containing session state.

        Returns:
            Dictionary of headers to include in MCP requests.
        """
        settings = get_settings()
        headers: dict[str, str] = {}

        # Try session state first (from user's JWT)
        client_id = context.state.get(LIGHTSPEED_CLIENT_ID_KEY)
        client_secret = context.state.get(LIGHTSPEED_CLIENT_SECRET_KEY)

        # Fallback to agent-level config from environment
        if not client_id:
            client_id = settings.lightspeed_client_id
            if client_id:
                logger.debug("Using agent-level lightspeed_client_id")
        else:
            logger.debug("Using per-user lightspeed_client_id from session")

        if not client_secret:
            client_secret = settings.lightspeed_client_secret
            if client_secret:
                logger.debug("Using agent-level lightspeed_client_secret")
        else:
            logger.debug("Using per-user lightspeed_client_secret from session")

        # Build headers
        if client_id:
            headers["lightspeed-client-id"] = client_id
        if client_secret:
            headers["lightspeed-client-secret"] = client_secret

        if not headers:
            logger.warning("No lightspeed credentials available for MCP request")

        return headers

    return header_provider
