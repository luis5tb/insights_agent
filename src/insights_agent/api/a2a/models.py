"""A2A protocol data models using the official a2a-sdk.

This module re-exports types from the a2a-sdk and adds custom extensions
for DCR (Dynamic Client Registration) and OAuth security schemes.
"""

from enum import Enum
from typing import Any, Literal

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
from pydantic import BaseModel, Field

# Re-export SDK types for convenience
__all__ = [
    # SDK types
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
]


class A2AErrorCode(int, Enum):
    """A2A protocol error codes (JSON-RPC 2.0 compatible)."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    TASK_NOT_FOUND = -32001
    TASK_CANCELLED = -32002
    AUTHENTICATION_REQUIRED = -32003
    UNAUTHORIZED = -32004
    RATE_LIMITED = -32005


class A2AError(BaseModel):
    """A2A protocol error response."""

    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: dict[str, Any] | None = Field(None, description="Additional error data")


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request structure."""

    jsonrpc: Literal["2.0"] = "2.0"
    method: str = Field(..., description="RPC method name")
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters")
    id: str | int = Field(..., description="Request identifier")


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response structure."""

    jsonrpc: Literal["2.0"] = "2.0"
    result: Any | None = Field(None, description="Method result")
    error: A2AError | None = Field(None, description="Error if failed")
    id: str | int = Field(..., description="Request identifier")


class DCRExtension(BaseModel):
    """Dynamic Client Registration extension for OAuth 2.0."""

    endpoint: str = Field(..., description="DCR endpoint URL")
    supported_grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code"],
        alias="supportedGrantTypes",
        description="Supported OAuth grant types",
    )

    class Config:
        populate_by_name = True


class OAuthSecurityScheme(BaseModel):
    """OAuth 2.0 security scheme definition."""

    type: Literal["oauth2"] = "oauth2"
    description: str | None = None
    flows: dict[str, Any] = Field(
        default_factory=dict,
        description="OAuth 2.0 flows configuration",
    )


class SecurityRequirement(BaseModel):
    """Security requirement for accessing the agent."""

    scheme: str = Field(..., description="Security scheme name")
    scopes: list[str] = Field(default_factory=list, description="Required scopes")


class AgentInterface(BaseModel):
    """Agent protocol interface binding."""

    protocol: str = Field(..., description="Protocol type (e.g., 'jsonrpc/http')")
    url: str = Field(..., description="Endpoint URL for this interface")


class SendMessageRequest(BaseModel):
    """Request payload for SendMessage operation.

    Wrapper around MessageSendParams for API compatibility.
    """

    message: Message = Field(..., description="Message to send")
    configuration: MessageSendConfiguration | None = Field(
        None,
        description="Request configuration",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )


class SendMessageResponse(BaseModel):
    """Response for SendMessage operation."""

    task: Task = Field(..., description="The created or updated task")
