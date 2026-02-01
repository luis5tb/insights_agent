"""Simple usage tracking plugin for aggregate token and tool metrics."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class AggregateUsage:
    """Aggregate usage statistics across all requests."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_requests: int = 0
    total_tool_calls: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_requests": self.total_requests,
            "total_tool_calls": self.total_tool_calls,
        }


# Global aggregate usage tracker
_aggregate_usage = AggregateUsage()


def get_aggregate_usage() -> AggregateUsage:
    """Get current aggregate usage statistics."""
    return _aggregate_usage


def reset_aggregate_usage() -> None:
    """Reset aggregate usage statistics (useful for testing)."""
    global _aggregate_usage
    _aggregate_usage = AggregateUsage()


class UsageTrackingPlugin(BasePlugin):
    """ADK Plugin for tracking aggregate token and tool usage.

    This plugin tracks:
    - Total input/output tokens across all LLM calls
    - Total number of requests
    - Total number of tool/MCP calls

    Usage is stored in a global counter accessible via get_aggregate_usage().
    """

    def __init__(self):
        super().__init__(name="usage_tracking")

    async def before_run_callback(self, *, invocation_context) -> None:
        """Track request count at start of each run."""
        _aggregate_usage.total_requests += 1
        logger.debug(f"Request #{_aggregate_usage.total_requests} started")
        return None

    async def after_model_callback(
        self,
        *,
        callback_context,
        llm_response: LlmResponse,
    ) -> Optional[LlmResponse]:
        """Track token usage from LLM responses."""
        if llm_response.usage_metadata:
            usage = llm_response.usage_metadata
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0

            _aggregate_usage.total_input_tokens += input_tokens
            _aggregate_usage.total_output_tokens += output_tokens

            logger.debug(
                f"Tokens: in={input_tokens}, out={output_tokens}, "
                f"totals: in={_aggregate_usage.total_input_tokens}, "
                f"out={_aggregate_usage.total_output_tokens}"
            )

        return None  # Don't modify the response

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context,
        result: dict,
    ) -> Optional[dict]:
        """Track tool/MCP calls."""
        _aggregate_usage.total_tool_calls += 1
        tool_name = getattr(tool, "name", type(tool).__name__)
        logger.debug(
            f"Tool call: {tool_name}, total calls: {_aggregate_usage.total_tool_calls}"
        )
        return None  # Don't modify the result
