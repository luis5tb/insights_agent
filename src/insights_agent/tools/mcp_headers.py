"""Header provider for MCP toolset to inject authentication credentials."""

import logging
from typing import TYPE_CHECKING

from insights_agent.config import get_settings

if TYPE_CHECKING:
    from google.adk.agents.readonly_context import ReadonlyContext

logger = logging.getLogger(__name__)

# Session state key for storing user's access token
ACCESS_TOKEN_KEY = "user_access_token"


def create_mcp_header_provider():
    """Create a header provider function for McpToolset.

    The returned function provides authentication headers for MCP requests:
    1. If user's access token is in session state, pass it as Authorization: Bearer
    2. Otherwise, fall back to agent-level credentials from environment variables

    Returns:
        A callable that takes ReadonlyContext and returns headers dict.
    """

    def header_provider(context: "ReadonlyContext") -> dict[str, str]:
        """Provide headers for MCP requests based on session context.

        Credential resolution order:
        1. User's access token from session state -> Authorization: Bearer
        2. Environment variables -> lightspeed-client-id/secret headers

        Args:
            context: The readonly context containing session state.

        Returns:
            Dictionary of headers to include in MCP requests.
        """
        settings = get_settings()
        headers: dict[str, str] = {}

        # Check for user's access token first (from authenticated request)
        access_token = context.state.get(ACCESS_TOKEN_KEY)

        if access_token:
            # User is authenticated - pass their token to MCP
            headers["Authorization"] = f"Bearer {access_token}"
            logger.debug("Using user's access token for MCP authentication")
        else:
            # Fallback to agent-level credentials from environment
            client_id = settings.lightspeed_client_id
            client_secret = settings.lightspeed_client_secret

            if client_id:
                headers["lightspeed-client-id"] = client_id
            if client_secret:
                headers["lightspeed-client-secret"] = client_secret

            if client_id or client_secret:
                logger.debug("Using agent-level credentials for MCP authentication")
            else:
                logger.warning("No credentials available for MCP request")

        return headers

    return header_provider
