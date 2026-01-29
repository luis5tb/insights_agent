"""Header provider for MCP toolset to inject authentication credentials."""

import logging
from typing import TYPE_CHECKING

from insights_agent.config import get_settings

if TYPE_CHECKING:
    from google.adk.agents.readonly_context import ReadonlyContext

logger = logging.getLogger(__name__)


def create_mcp_header_provider():
    """Create a header provider function for McpToolset.

    The returned function provides authentication headers for MCP requests
    using the agent-level credentials from environment variables.

    Returns:
        A callable that takes ReadonlyContext and returns headers dict.
    """

    def header_provider(context: "ReadonlyContext") -> dict[str, str]:
        """Provide headers for MCP requests.

        Uses LIGHTSPEED_CLIENT_ID and LIGHTSPEED_CLIENT_SECRET from
        environment variables.

        Args:
            context: The readonly context (unused, but required by interface).

        Returns:
            Dictionary of headers to include in MCP requests.
        """
        settings = get_settings()
        headers: dict[str, str] = {}

        if settings.lightspeed_client_id:
            headers["lightspeed-client-id"] = settings.lightspeed_client_id
        if settings.lightspeed_client_secret:
            headers["lightspeed-client-secret"] = settings.lightspeed_client_secret

        if headers:
            logger.debug("Using lightspeed credentials from environment")
        else:
            logger.warning("No lightspeed credentials configured")

        return headers

    return header_provider
