"""AgentCard builder for the Insights Agent using a2a-sdk."""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentProvider,
    AgentSkill,
    AuthorizationCodeOAuthFlow,
    OAuth2SecurityScheme,
    OAuthFlows,
)

from insights_agent.config import get_settings
from insights_agent.tools.skills import get_skills_for_agent_card


def _build_skills() -> list[AgentSkill]:
    """Build AgentSkill objects from MCP skills."""
    settings = get_settings()
    raw_skills = get_skills_for_agent_card(read_only=settings.mcp_read_only)

    skills = []
    for skill_data in raw_skills:
        skill = AgentSkill(
            id=skill_data["id"],
            name=skill_data["name"],
            description=skill_data["description"],
            tags=skill_data.get("tags", []),
            examples=skill_data.get("examples", []),
        )
        skills.append(skill)

    return skills


def _build_oauth_security_scheme() -> OAuth2SecurityScheme:
    """Build OAuth 2.0 security scheme for Red Hat SSO."""
    settings = get_settings()

    auth_code_flow = AuthorizationCodeOAuthFlow(
        authorization_url=f"{settings.red_hat_sso_issuer}/protocol/openid-connect/auth",
        token_url=f"{settings.red_hat_sso_issuer}/protocol/openid-connect/token",
        scopes={
            "openid": "OpenID Connect scope",
            "profile": "User profile information",
            "email": "User email address",
        },
    )

    return OAuth2SecurityScheme(
        type="oauth2",
        description="Red Hat SSO OAuth 2.0 Authentication",
        flows=OAuthFlows(authorization_code=auth_code_flow),
    )


def _build_dcr_extension() -> AgentExtension:
    """Build DCR extension for Google Marketplace integration.

    Provides two endpoints for DCR:
    - /oauth/register - RFC 7591 compliant path
    - /dcr - Google-compatible path (per Google's example)
    """
    settings = get_settings()

    return AgentExtension(
        uri="urn:google:agent:dcr",
        description="Dynamic Client Registration for OAuth 2.0",
        params={
            # Primary endpoint (RFC 7591 compliant)
            "endpoint": f"{settings.agent_provider_url}/oauth/register",
            # Alternative endpoint (Google example path)
            "alternativeEndpoint": f"{settings.agent_provider_url}/dcr",
            "supportedGrantTypes": ["authorization_code", "refresh_token"],
        },
    )


def _build_capabilities() -> AgentCapabilities:
    """Build agent capabilities with extensions."""
    dcr_extension = _build_dcr_extension()

    return AgentCapabilities(
        streaming=True,
        push_notifications=False,
        state_transition_history=False,
        extensions=[dcr_extension],
    )


def build_agent_card() -> AgentCard:
    """Build the complete AgentCard for the Insights Agent.

    Returns:
        Configured AgentCard instance with all capabilities,
        skills, and security requirements.
    """
    settings = get_settings()

    provider = AgentProvider(
        organization="Red Hat",
        url="https://www.redhat.com",
    )

    oauth_scheme = _build_oauth_security_scheme()
    capabilities = _build_capabilities()
    skills = _build_skills()

    agent_card = AgentCard(
        name=settings.agent_name,
        description=settings.agent_description,
        version="0.1.0",
        url=f"{settings.agent_provider_url}/",
        protocol_version="0.2.3",
        provider=provider,
        capabilities=capabilities,
        skills=skills,
        security_schemes={
            "redhat_sso": oauth_scheme,
        },
        security=[
            {"redhat_sso": ["openid", "profile"]},
        ],
        default_input_modes=["text"],
        default_output_modes=["text"],
    )

    return agent_card


def get_agent_card_dict() -> dict:
    """Get the AgentCard as a dictionary for JSON serialization.

    Returns:
        AgentCard data as a dictionary with proper field aliasing.
    """
    agent_card = build_agent_card()

    # Convert to dict, handling both Pydantic v1 and v2 style
    if hasattr(agent_card, "model_dump"):
        return agent_card.model_dump(by_alias=True, exclude_none=True)
    else:
        return agent_card.dict(by_alias=True, exclude_none=True)
