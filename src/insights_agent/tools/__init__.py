"""Tools module for MCP integration with Red Hat Insights."""

from insights_agent.tools.insights_tools import (
    ALL_INSIGHTS_TOOLS,
    READ_ONLY_TOOLS,
    create_insights_toolset,
    get_insights_tools_for_cloud_run,
)
from insights_agent.tools.mcp_config import MCPServerConfig, setup_mcp_environment
from insights_agent.tools.mcp_headers import create_mcp_header_provider
from insights_agent.tools.skills import (
    ALL_SKILLS,
    READ_ONLY_SKILLS,
    Skill,
    get_skills_for_agent_card,
)

__all__ = [
    # MCP Config
    "MCPServerConfig",
    "setup_mcp_environment",
    # MCP Headers
    "create_mcp_header_provider",
    # Toolset creation
    "create_insights_toolset",
    "get_insights_tools_for_cloud_run",
    # Tool lists
    "ALL_INSIGHTS_TOOLS",
    "READ_ONLY_TOOLS",
    # Skills
    "Skill",
    "ALL_SKILLS",
    "READ_ONLY_SKILLS",
    "get_skills_for_agent_card",
]
