"""A2A (Agent-to-Agent) protocol implementation using official a2a-sdk."""

from insights_agent.api.a2a.agent_card import (
    build_agent_card,
    get_agent_card_dict,
)
from insights_agent.api.a2a.models import (
    # Custom types
    A2AError,
    A2AErrorCode,
    # SDK types
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    Artifact,
    DataPart,
    DCRExtension,
    FilePart,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    MessageSendConfiguration,
    OAuthSecurityScheme,
    Part,
    Role,
    SecurityRequirement,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from insights_agent.api.a2a.router import router as a2a_router

__all__ = [
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
    # Custom types
    "A2AError",
    "A2AErrorCode",
    "AgentInterface",
    "DCRExtension",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "OAuthSecurityScheme",
    "SecurityRequirement",
    "SendMessageRequest",
    "SendMessageResponse",
    # Router
    "a2a_router",
]
