"""Simplified metering module.

Token and tool usage is tracked via the UsageTrackingPlugin in the ADK runner.
This middleware just provides request logging.
"""

from insights_agent.metering.middleware import MeteringMiddleware

__all__ = [
    "MeteringMiddleware",
]
