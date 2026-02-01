"""A2A protocol data models using the official a2a-sdk.

This module re-exports types from the a2a-sdk for convenience.
The ADK integration handles all JSON-RPC protocol details internally.
"""

# Import core types from a2a-sdk
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    AgentSkill,
    Artifact,
    DataPart,
    FilePart,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

# Re-export SDK types for convenience
__all__ = [
    "AgentCard",
    "AgentCapabilities",
    "AgentProvider",
    "AgentSkill",
    "Artifact",
    "DataPart",
    "FilePart",
    "Message",
    "MessageSendConfiguration",
    "MessageSendParams",
    "Part",
    "Role",
    "Task",
    "TaskArtifactUpdateEvent",
    "TaskState",
    "TaskStatus",
    "TaskStatusUpdateEvent",
    "TextPart",
]
