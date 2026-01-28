"""Root agent module for ADK CLI compatibility.

This file is required at the project root for `adk web` and `adk run` commands.
It re-exports the root_agent from the main package.
"""

from dotenv import load_dotenv

# Load environment variables before importing agent
load_dotenv()

from insights_agent.core.agent import root_agent  # noqa: E402

# Export root_agent for ADK CLI
__all__ = ["root_agent"]
