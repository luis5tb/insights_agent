"""A2A (Agent-to-Agent) protocol implementation using official a2a-sdk.

This module uses ADK's built-in A2A integration which handles:
- SSE streaming with proper event formatting
- Task state management
- Event conversion between ADK and A2A formats
- JSON-RPC 2.0 protocol compliance

For A2A types (AgentCard, Message, Task, etc.), import directly from a2a.types.
"""

from lightspeed_agent.api.a2a.a2a_setup import setup_a2a_routes
from lightspeed_agent.api.a2a.agent_card import (
    build_agent_card,
    get_agent_card_dict,
)

__all__ = [
    # A2A Setup
    "setup_a2a_routes",
    # Agent Card
    "build_agent_card",
    "get_agent_card_dict",
]
