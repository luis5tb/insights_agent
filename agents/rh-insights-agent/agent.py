"""Agent definition for ADK CLI.

This module defines the root_agent for the `adk web` command.
"""

from dotenv import load_dotenv

# Load environment variables before importing agent
load_dotenv()

from insights_agent.core.agent import root_agent  # noqa: E402, F401
