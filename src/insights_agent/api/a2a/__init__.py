"""A2A (Agent-to-Agent) protocol implementation using official a2a-sdk.

This module uses ADK's built-in A2A integration which handles:
- SSE streaming with proper event formatting
- Task state management
- Event conversion between ADK and A2A formats
- JSON-RPC 2.0 protocol compliance
"""

from insights_agent.api.a2a.a2a_setup import setup_a2a_routes
from insights_agent.api.a2a.agent_card import (
    build_agent_card,
    get_agent_card_dict,
)
from insights_agent.api.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    AgentSkill,
    Artifact,
    DataPart,
    FilePart,
    Message,
    MessageSendConfiguration,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)

__all__ = [
    # A2A Setup
    "setup_a2a_routes",
    # Agent Card
    "build_agent_card",
    "get_agent_card_dict",
    # SDK types
    "AgentCapabilities",
    "AgentCard",
    "AgentProvider",
    "AgentSkill",
    "Artifact",
    "DataPart",
    "FilePart",
    "Message",
    "MessageSendConfiguration",
    "Part",
    "Role",
    "Task",
    "TaskState",
    "TaskStatus",
    "TextPart",
]
