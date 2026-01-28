"""MCP server configuration and connection management."""

import os
from dataclasses import dataclass
from typing import Literal

from insights_agent.config import get_settings


@dataclass
class MCPServerConfig:
    """Configuration for the Red Hat Insights MCP server."""

    transport_mode: Literal["stdio", "http", "sse"]
    client_id: str
    client_secret: str
    server_url: str | None = None
    read_only: bool = True
    container_image: str = "ghcr.io/redhatinsights/red-hat-lightspeed-mcp:latest"

    @classmethod
    def from_settings(cls) -> "MCPServerConfig":
        """Create configuration from application settings."""
        settings = get_settings()
        return cls(
            transport_mode=settings.mcp_transport_mode,
            client_id=settings.lightspeed_client_id,
            client_secret=settings.lightspeed_client_secret,
            server_url=settings.mcp_server_url,
            read_only=settings.mcp_read_only,
        )

    def get_stdio_command(self) -> str:
        """Get the command for stdio transport."""
        return "podman"

    def get_stdio_args(self) -> list[str]:
        """Get the arguments for stdio transport."""
        args = [
            "run",
            "--env", "LIGHTSPEED_CLIENT_ID",
            "--env", "LIGHTSPEED_CLIENT_SECRET",
            "--interactive",
            "--rm",
            self.container_image,
        ]
        if self.read_only:
            args.append("--read-only")
        return args

    def get_stdio_env(self) -> dict[str, str]:
        """Get environment variables for stdio transport."""
        return {
            "LIGHTSPEED_CLIENT_ID": self.client_id,
            "LIGHTSPEED_CLIENT_SECRET": self.client_secret,
        }

    def get_http_url(self) -> str:
        """Get the URL for HTTP transport."""
        return f"{self.server_url}/mcp"

    def get_http_headers(self) -> dict[str, str]:
        """Get headers for HTTP transport."""
        return {
            "lightspeed-client-id": self.client_id,
            "lightspeed-client-secret": self.client_secret,
        }


def setup_mcp_environment(config: MCPServerConfig) -> None:
    """Set up environment variables for MCP connection.

    Args:
        config: MCP server configuration.
    """
    os.environ["LIGHTSPEED_CLIENT_ID"] = config.client_id
    os.environ["LIGHTSPEED_CLIENT_SECRET"] = config.client_secret
