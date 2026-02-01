"""A2A protocol setup using ADK's built-in A2A integration.

This module sets up the A2A protocol endpoints using the google-adk
and a2a-sdk libraries, which handle all the complexity of SSE streaming,
task management, and event conversion automatically.
"""

import logging

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.apps import App
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from insights_agent.api.a2a.agent_card import build_agent_card
from insights_agent.api.a2a.usage_plugin import UsageTrackingPlugin
from insights_agent.config import get_settings
from insights_agent.core import create_agent

logger = logging.getLogger(__name__)


def _create_runner() -> Runner:
    """Create a Runner for the ADK agent with usage tracking.

    Returns:
        Configured Runner instance with in-memory services and usage plugin.
    """
    settings = get_settings()
    agent = create_agent()

    # Create App with usage tracking plugin
    app = App(
        name=settings.agent_name,
        root_agent=agent,
        plugins=[UsageTrackingPlugin()],
    )

    return Runner(
        app=app,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )


def setup_a2a_routes(app: FastAPI) -> None:
    """Set up A2A protocol routes on the FastAPI application.

    This function configures the A2A endpoints using the official
    ADK and a2a-sdk integration, which handles:
    - JSON-RPC message handling
    - SSE streaming with proper event formatting
    - Task state management
    - Event conversion between ADK and A2A formats

    Args:
        app: The FastAPI application to add routes to.
    """
    settings = get_settings()

    # Create A2A components
    task_store = InMemoryTaskStore()

    # A2aAgentExecutor accepts a Runner or a callable that returns one
    # Using a callable allows lazy initialization
    agent_executor = A2aAgentExecutor(runner=_create_runner)

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
    )

    # Build our custom AgentCard with OAuth security schemes
    agent_card = build_agent_card()

    # Create the A2A application
    a2a_app = A2AFastAPIApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # Add A2A routes to the FastAPI app
    # - POST at rpc_url for JSON-RPC requests (message/send, message/stream, etc.)
    # - GET at agent_card_url for the AgentCard
    a2a_app.add_routes_to_app(
        app,
        agent_card_url="/.well-known/agent.json",
        rpc_url="/",  # Root URL for A2A Inspector compatibility
    )

    logger.info(
        f"A2A routes configured: AgentCard at /.well-known/agent.json, "
        f"JSON-RPC at /, agent_url={settings.agent_provider_url}"
    )
