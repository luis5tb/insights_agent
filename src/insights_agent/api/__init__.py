"""API module for A2A endpoints, AgentCard, and OAuth."""

from insights_agent.api.a2a import build_agent_card, get_agent_card_dict, setup_a2a_routes
from insights_agent.api.app import create_app

__all__ = [
    "build_agent_card",
    "create_app",
    "get_agent_card_dict",
    "setup_a2a_routes",
]
