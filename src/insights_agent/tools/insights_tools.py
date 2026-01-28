"""Red Hat Insights MCP tools integration for Google ADK."""

import os
from typing import TYPE_CHECKING

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams, StdioConnectionParams
from mcp import StdioServerParameters

from insights_agent.config import get_settings
from insights_agent.tools.mcp_config import MCPServerConfig, setup_mcp_environment

if TYPE_CHECKING:
    from google.adk.tools import BaseTool


def create_insights_toolset(
    config: MCPServerConfig | None = None,
    tool_filter: list[str] | None = None,
) -> McpToolset:
    """Create an MCP toolset for Red Hat Insights.

    Args:
        config: Optional MCP server configuration. If None, loads from settings.
        tool_filter: Optional list of tool names to expose. If None, all tools are exposed.

    Returns:
        Configured McpToolset instance.
    """
    if config is None:
        config = MCPServerConfig.from_settings()

    # Set up environment for MCP connection
    setup_mcp_environment(config)

    if config.transport_mode == "stdio":
        return _create_stdio_toolset(config, tool_filter)
    elif config.transport_mode == "sse":
        return _create_sse_toolset(config, tool_filter)
    elif config.transport_mode == "http":
        return _create_http_toolset(config, tool_filter)
    else:
        raise ValueError(f"Unsupported transport mode: {config.transport_mode}")


def _create_stdio_toolset(
    config: MCPServerConfig,
    tool_filter: list[str] | None = None,
) -> McpToolset:
    """Create MCP toolset using stdio transport.

    This is the default mode for local development using containers.
    """
    server_params = StdioServerParameters(
        command=config.get_stdio_command(),
        args=config.get_stdio_args(),
        env=config.get_stdio_env(),
    )

    connection_params = StdioConnectionParams(server_params=server_params)

    return McpToolset(
        connection_params=connection_params,
        tool_filter=tool_filter,
    )


def _create_sse_toolset(
    config: MCPServerConfig,
    tool_filter: list[str] | None = None,
) -> McpToolset:
    """Create MCP toolset using SSE transport.

    This is recommended for production deployments.
    """
    connection_params = SseConnectionParams(
        url=f"{config.server_url}/sse",
        headers=config.get_http_headers(),
    )

    return McpToolset(
        connection_params=connection_params,
        tool_filter=tool_filter,
    )


def _create_http_toolset(
    config: MCPServerConfig,
    tool_filter: list[str] | None = None,
) -> McpToolset:
    """Create MCP toolset using HTTP transport."""
    # HTTP transport uses SSE connection params with different URL
    connection_params = SseConnectionParams(
        url=config.get_http_url(),
        headers=config.get_http_headers(),
    )

    return McpToolset(
        connection_params=connection_params,
        tool_filter=tool_filter,
    )


def get_insights_tools_for_cloud_run() -> McpToolset:
    """Get MCP toolset configured for Cloud Run deployment.

    In Cloud Run, we prefer SSE transport to a separately deployed MCP server.
    Falls back to stdio for local development.

    Returns:
        Configured McpToolset instance.
    """
    config = MCPServerConfig.from_settings()

    # Check if running in Cloud Run
    if os.getenv("K_SERVICE"):
        # Use SSE transport in Cloud Run
        config.transport_mode = "sse"
    else:
        # Use stdio for local development
        config.transport_mode = "stdio"

    return create_insights_toolset(config)


# Tool categories for filtering
ADVISOR_TOOLS = [
    "get_active_rules",
    "get_rule_from_node_id",
    "get_rule_details",
    "get_hosts_hitting_a_rule",
    "get_hosts_details_hitting_a_rule",
    "get_rule_by_text_search",
    "get_recommendations_statistics",
]

INVENTORY_TOOLS = [
    "list_hosts",
    "get_host_details",
    "get_host_system_profile",
    "get_host_tags",
    "find_host_by_name",
]

VULNERABILITY_TOOLS = [
    "get_cves",
    "get_cve",
    "get_cve_systems",
    "get_system_cves",
    "get_systems",
    "explain_cves",
]

REMEDIATION_TOOLS = [
    "create_vulnerability_playbook",
]

PLANNING_TOOLS = [
    "get_upcoming_changes",
    "get_appstreams_lifecycle",
    "get_rhel_lifecycle",
    "get_relevant_upcoming_changes",
]

IMAGE_BUILDER_TOOLS = [
    "get_blueprints",
    "get_blueprint_details",
    "create_blueprint",
    "update_blueprint",
    "blueprint_compose",
    "get_composes",
    "get_compose_details",
    "get_distributions",
    "get_org_id",
]

RHSM_TOOLS = [
    "get_activation_keys",
    "get_activation_key",
]

RBAC_TOOLS = [
    "get_all_access",
]

CONTENT_SOURCES_TOOLS = [
    "list_repositories",
]

# All available tools
ALL_INSIGHTS_TOOLS = (
    ADVISOR_TOOLS
    + INVENTORY_TOOLS
    + VULNERABILITY_TOOLS
    + REMEDIATION_TOOLS
    + PLANNING_TOOLS
    + IMAGE_BUILDER_TOOLS
    + RHSM_TOOLS
    + RBAC_TOOLS
    + CONTENT_SOURCES_TOOLS
)

# Read-only tools (safe for restricted access)
READ_ONLY_TOOLS = (
    ADVISOR_TOOLS
    + INVENTORY_TOOLS
    + VULNERABILITY_TOOLS
    + PLANNING_TOOLS
    + RHSM_TOOLS
    + RBAC_TOOLS
    + CONTENT_SOURCES_TOOLS
    + [
        "get_blueprints",
        "get_blueprint_details",
        "get_composes",
        "get_compose_details",
        "get_distributions",
        "get_org_id",
    ]
)
