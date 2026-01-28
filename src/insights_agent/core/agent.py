"""Core agent definition using Google ADK with Gemini 2.5 Flash."""

import logging
import os

from google.adk.agents import LlmAgent

from insights_agent.config import get_settings

logger = logging.getLogger(__name__)

# Agent instruction describing its capabilities
AGENT_INSTRUCTION = """You are the Red Hat Insights Agent, an AI assistant specialized in
helping users manage their Red Hat infrastructure. You have access to the following
Red Hat Insights capabilities:

## Advisor
- Analyze system configurations and provide recommendations
- Identify potential issues before they impact your systems
- Provide guidance on best practices

## Inventory
- Query and manage system inventory
- Track registered systems and their properties
- Search for systems by various attributes

## Vulnerability
- Analyze security vulnerabilities affecting your systems
- Provide CVE information and remediation guidance
- Prioritize vulnerabilities based on risk

## Remediations
- Create and manage remediation playbooks
- Guide users through issue resolution
- Track remediation progress

## Planning
- Help plan RHEL system upgrades and migrations
- Provide roadmap recommendations
- Assess upgrade readiness

## Image Builder
- Assist with creating custom RHEL images
- Configure image compositions
- Manage image build processes

## Subscription Management
- View activation keys for system registration
- Access subscription information

## Content Sources
- List available content repositories
- Query repository information

When responding to users:
1. Always be helpful and provide clear, actionable information
2. If you need more context, ask clarifying questions
3. When providing remediation steps, be specific and detailed
4. Respect the read-only mode when enabled - inform users if write operations are restricted
5. Provide security-conscious recommendations
6. When displaying lists of systems or vulnerabilities, format them clearly
7. For CVEs, always include severity information when available
"""


def _setup_environment() -> None:
    """Set up environment variables for Google ADK."""
    settings = get_settings()

    # Configure Vertex AI or Google AI Studio
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(settings.google_genai_use_vertexai).upper()

    if settings.google_genai_use_vertexai:
        if settings.google_cloud_project:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location
    elif settings.google_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key


def create_agent() -> LlmAgent:
    """Create the Insights Agent with MCP tools if credentials are configured.

    This function creates an LlmAgent with the Red Hat Insights MCP toolset
    automatically configured if MCP credentials are available. If credentials
    are not configured or MCP connection fails, the agent is created without tools.

    Returns:
        Configured LlmAgent instance.
    """
    _setup_environment()
    settings = get_settings()

    tools: list = []

    # Only attempt MCP connection if credentials are configured
    if settings.lightspeed_client_id and settings.lightspeed_client_secret:
        try:
            from insights_agent.tools import READ_ONLY_TOOLS, create_insights_toolset

            tool_filter = READ_ONLY_TOOLS if settings.mcp_read_only else None
            mcp_toolset = create_insights_toolset(tool_filter=tool_filter)
            tools = [mcp_toolset]
            logger.info(
                "Created agent with MCP tools",
                extra={"read_only": settings.mcp_read_only, "model": settings.gemini_model},
            )
        except Exception as e:
            logger.warning(f"Failed to create MCP toolset: {e}")
    else:
        logger.info("MCP credentials not configured, agent created without tools")

    return LlmAgent(
        name=settings.agent_name,
        model=settings.gemini_model,
        description=settings.agent_description,
        instruction=AGENT_INSTRUCTION,
        tools=tools,
    )


# Root agent instance for ADK CLI compatibility
root_agent = create_agent()
