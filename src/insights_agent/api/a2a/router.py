"""A2A protocol router with endpoints for agent communication."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from insights_agent.api.a2a.agent_card import get_agent_card_dict
from insights_agent.api.a2a.models import (
    A2AError,
    A2AErrorCode,
    Artifact,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from insights_agent.metering.service import MeteringService, get_metering_service

logger = logging.getLogger(__name__)


@dataclass
class UsageStats:
    """Accumulated usage statistics from agent invocation."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: list[str] = field(default_factory=list)


def _get_order_id_from_request(request: Request) -> str | None:
    """Extract order ID from request for metering.

    Args:
        request: FastAPI request object.

    Returns:
        Order ID if found, None otherwise.
    """
    # Check request state first (set by auth middleware)
    if hasattr(request.state, "user") and request.state.user:
        order_id = request.state.user.metadata.get("order_id")
        if order_id:
            return order_id

    # Check X-Order-ID header for internal/trusted calls
    order_id = request.headers.get("X-Order-ID")
    if order_id:
        return order_id

    return None

router = APIRouter(tags=["A2A Protocol"])

# In-memory task storage (replace with database in production)
_tasks: dict[str, Task] = {}


def _ensure_message_id(message_data: dict[str, Any]) -> dict[str, Any]:
    """Ensure message has a messageId, generating one if missing.

    Args:
        message_data: Raw message dictionary from request.

    Returns:
        Message dictionary with messageId ensured.
    """
    if "messageId" not in message_data and "message_id" not in message_data:
        message_data["messageId"] = str(uuid4())
    return message_data


def _preprocess_request_params(params: dict[str, Any]) -> dict[str, Any]:
    """Preprocess request params to ensure required fields.

    Args:
        params: Raw request parameters.

    Returns:
        Preprocessed parameters with required fields ensured.
    """
    if "message" in params and isinstance(params["message"], dict):
        params["message"] = _ensure_message_id(params["message"])
    return params


@router.get("/.well-known/agent.json")
async def get_agent_card() -> JSONResponse:
    """Get the AgentCard for this agent.

    This endpoint provides the agent's metadata document including
    capabilities, skills, and authentication requirements.

    Returns:
        AgentCard JSON document.
    """
    agent_card = get_agent_card_dict()
    return JSONResponse(content=agent_card)


@router.get("/.well-known/agent-card.json")
async def get_agent_card_alt() -> JSONResponse:
    """Alternative endpoint for AgentCard (ADK compatibility).

    Returns:
        AgentCard JSON document.
    """
    return await get_agent_card()


async def _process_message(message: Message, order_id: str | None = None) -> Task:
    """Process an incoming message and create a task.

    This is the core message handler that invokes the agent.

    Args:
        message: The incoming message to process.
        order_id: Order ID for metering (optional).

    Returns:
        Task object with the result.
    """
    task_id = str(uuid4())
    context_id = message.context_id or str(uuid4())

    # Create initial task with TaskStatus
    task = Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.working),
    )
    _tasks[task_id] = task

    try:
        # Extract text from message parts
        # Parts may be wrapped in a Part discriminated union with a 'root' attribute
        user_text = ""
        for part in message.parts or []:
            # Handle wrapped parts (Part union type)
            actual_part = part.root if hasattr(part, "root") else part
            if hasattr(actual_part, "text") and actual_part.text:
                user_text += actual_part.text

        if not user_text:
            raise ValueError("No text content in message")

        # Import agent here to avoid circular imports
        from insights_agent.core import create_agent

        # Create agent and run
        agent = create_agent()

        response_text, usage_stats = await _invoke_agent(
            agent, user_text, context_id, order_id
        )

        # Track usage metrics if we have an order_id
        if order_id:
            await _track_usage_metrics(
                order_id=order_id,
                usage_stats=usage_stats,
                context_id=context_id,
                task_id=task_id,
            )

        # Create artifact with response using SDK types
        artifact = Artifact(
            artifact_id=str(uuid4()),
            parts=[TextPart(text=response_text)],
            name="response",
            description="Agent response",
        )

        task.artifacts = [artifact]
        task.status = TaskStatus(state=TaskState.completed)

        # Add agent response to history
        agent_message = Message(
            messageId=str(uuid4()),
            role="agent",
            parts=[TextPart(text=response_text)],
            contextId=context_id,
            taskId=task_id,
        )
        task.history = [message, agent_message]

    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        task.status = TaskStatus(state=TaskState.failed)
        task.artifacts = [
            Artifact(
                artifact_id=str(uuid4()),
                parts=[TextPart(text=f"Error: {str(e)}")],
                name="error",
            )
        ]

    _tasks[task_id] = task
    return task


async def _track_usage_metrics(
    order_id: str,
    usage_stats: UsageStats,
    context_id: str | None = None,
    task_id: str | None = None,
) -> None:
    """Track usage metrics from agent invocation.

    Args:
        order_id: Order ID for billing.
        usage_stats: Accumulated usage statistics.
        context_id: Conversation context ID.
        task_id: Associated task ID.
    """
    try:
        metering = get_metering_service()

        # Track token usage
        if usage_stats.input_tokens > 0 or usage_stats.output_tokens > 0:
            await metering.track_token_usage(
                order_id=order_id,
                input_tokens=usage_stats.input_tokens,
                output_tokens=usage_stats.output_tokens,
                context_id=context_id,
                task_id=task_id,
            )
            logger.debug(
                f"Tracked token usage for order {order_id}: "
                f"input={usage_stats.input_tokens}, output={usage_stats.output_tokens}"
            )

        # Track MCP/tool calls
        for tool_name in usage_stats.tool_calls:
            await metering.track_mcp_call(
                order_id=order_id,
                tool_name=tool_name,
                context_id=context_id,
                task_id=task_id,
            )
            logger.debug(f"Tracked MCP call for order {order_id}: {tool_name}")

    except Exception as e:
        # Don't fail the request due to metering errors
        logger.warning(f"Failed to track usage metrics: {e}")


async def _invoke_agent(
    agent: Any,
    user_text: str,
    context_id: str,
    order_id: str | None = None,
) -> tuple[str, UsageStats]:
    """Invoke the ADK agent with a user message.

    Args:
        agent: The ADK agent instance.
        user_text: User's message text.
        context_id: Conversation context ID.
        order_id: Order ID for metering (optional).

    Returns:
        Tuple of (agent's response text, usage statistics).
    """
    usage_stats = UsageStats()

    try:
        # Use ADK's Runner to execute the agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        # Create session service and runner
        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            app_name="insights-agent",
            session_service=session_service,
        )

        # Create session
        session = await session_service.create_session(
            app_name="insights-agent",
            user_id="a2a-user",
            session_id=context_id,
        )

        # Create user message content
        user_content = types.Content(
            role="user",
            parts=[types.Part(text=user_text)],
        )

        # Run agent and collect final response
        logger.debug(f"Invoking agent with message: {user_text[:100]}...")
        final_response_text = "No response generated."
        event_count = 0
        async for event in runner.run_async(
            session_id=session.id,
            user_id="a2a-user",
            new_message=user_content,
        ):
            event_count += 1
            logger.debug(f"Event {event_count}: author={getattr(event, 'author', 'N/A')}, "
                        f"is_final={event.is_final_response()}")

            # Track token usage from events with usage_metadata
            if hasattr(event, "usage_metadata") and event.usage_metadata:
                usage = event.usage_metadata
                # Accumulate token counts (some events may have partial counts)
                if hasattr(usage, "prompt_token_count") and usage.prompt_token_count:
                    usage_stats.input_tokens += usage.prompt_token_count
                if hasattr(usage, "candidates_token_count") and usage.candidates_token_count:
                    usage_stats.output_tokens += usage.candidates_token_count
                if hasattr(usage, "total_token_count") and usage.total_token_count:
                    usage_stats.total_tokens += usage.total_token_count

            # Track function/tool calls
            if hasattr(event, "get_function_calls"):
                func_calls = event.get_function_calls()
                if func_calls:
                    for func_call in func_calls:
                        tool_name = getattr(func_call, "name", "unknown")
                        usage_stats.tool_calls.append(tool_name)
                        logger.debug(f"Tool call detected: {tool_name}")

            # Check for final response using ADK's helper method
            if event.is_final_response():
                if event.content and event.content.parts:
                    # Collect text from all parts
                    text_parts = []
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        final_response_text = "".join(text_parts)
                        logger.debug(f"Final response: {final_response_text[:200]}...")
                break

        logger.debug(f"Total events processed: {event_count}")
        logger.debug(
            f"Usage stats: input_tokens={usage_stats.input_tokens}, "
            f"output_tokens={usage_stats.output_tokens}, "
            f"tool_calls={len(usage_stats.tool_calls)}"
        )
        return final_response_text, usage_stats

    except ImportError:
        # Fallback if ADK runner is not available
        logger.warning("ADK Runner not available, using fallback response")
        return (
            f"I received your message: '{user_text[:100]}...'. "
            "The agent is configured but the full ADK runtime is not available. "
            "Please ensure google-adk is properly installed.",
            usage_stats,
        )
    except Exception as e:
        logger.exception(f"Error invoking agent: {e}")
        return f"Error processing request: {str(e)}", usage_stats


@router.post("/a2a")
async def send_message(request: Request) -> JSONResponse:
    """A2A SendMessage endpoint (JSON-RPC 2.0).

    This endpoint handles synchronous message requests from other agents.

    Args:
        request: The incoming HTTP request with JSON-RPC payload.

    Returns:
        JSON-RPC response with task result.
    """
    try:
        body = await request.json()

        # Extract order_id for metering
        order_id = _get_order_id_from_request(request)

        # Handle JSON-RPC format
        if "jsonrpc" in body:
            rpc_request = JSONRPCRequest(**body)

            if rpc_request.method == "message/send":
                params = _preprocess_request_params(rpc_request.params)
                send_request = SendMessageRequest(**params)
                task = await _process_message(send_request.message, order_id=order_id)

                response = JSONRPCResponse(
                    result=SendMessageResponse(task=task).model_dump(by_alias=True),
                    id=rpc_request.id,
                )
                return JSONResponse(content=response.model_dump(by_alias=True, exclude_none=True))

            elif rpc_request.method == "tasks/get":
                task_id = rpc_request.params.get("taskId")
                if task_id and task_id in _tasks:
                    response = JSONRPCResponse(
                        result=_tasks[task_id].model_dump(by_alias=True),
                        id=rpc_request.id,
                    )
                else:
                    response = JSONRPCResponse(
                        error=A2AError(
                            code=A2AErrorCode.TASK_NOT_FOUND,
                            message=f"Task {task_id} not found",
                        ),
                        id=rpc_request.id,
                    )
                return JSONResponse(content=response.model_dump(by_alias=True, exclude_none=True))

            elif rpc_request.method == "tasks/cancel":
                task_id = rpc_request.params.get("taskId")
                if task_id and task_id in _tasks:
                    _tasks[task_id].status = TaskStatus(state=TaskState.canceled)
                    response = JSONRPCResponse(
                        result={"cancelled": True},
                        id=rpc_request.id,
                    )
                else:
                    response = JSONRPCResponse(
                        error=A2AError(
                            code=A2AErrorCode.TASK_NOT_FOUND,
                            message=f"Task {task_id} not found",
                        ),
                        id=rpc_request.id,
                    )
                return JSONResponse(content=response.model_dump(by_alias=True, exclude_none=True))

            else:
                response = JSONRPCResponse(
                    error=A2AError(
                        code=A2AErrorCode.METHOD_NOT_FOUND,
                        message=f"Method {rpc_request.method} not found",
                    ),
                    id=rpc_request.id,
                )
                return JSONResponse(
                    content=response.model_dump(by_alias=True, exclude_none=True),
                    status_code=404,
                )

        # Handle direct SendMessageRequest format
        body = _preprocess_request_params(body)
        send_request = SendMessageRequest(**body)
        task = await _process_message(send_request.message, order_id=order_id)

        return JSONResponse(
            content=SendMessageResponse(task=task).model_dump(by_alias=True, exclude_none=True)
        )

    except Exception as e:
        logger.exception(f"Error handling A2A request: {e}")
        error_response = JSONRPCResponse(
            error=A2AError(
                code=A2AErrorCode.INTERNAL_ERROR,
                message=str(e),
            ),
            id=body.get("id", 0) if isinstance(body, dict) else 0,
        )
        return JSONResponse(
            content=error_response.model_dump(by_alias=True, exclude_none=True),
            status_code=500,
        )


async def _stream_task_updates(task: Task) -> AsyncGenerator[str, None]:
    """Generate SSE events for task updates.

    Args:
        task: The task to stream updates for.

    Yields:
        SSE-formatted event strings.
    """
    # Send initial task state
    yield f"data: {task.model_dump_json(by_alias=True)}\n\n"

    # Poll for updates (in production, use proper async notifications)
    while task.status and task.status.state in (TaskState.submitted, TaskState.working):
        await asyncio.sleep(0.5)
        task = _tasks.get(task.id, task)
        yield f"data: {task.model_dump_json(by_alias=True)}\n\n"

    # Send final state
    yield f"data: {task.model_dump_json(by_alias=True)}\n\n"


@router.post("/a2a/stream")
async def send_streaming_message(request: Request) -> StreamingResponse:
    """A2A SendStreamingMessage endpoint.

    This endpoint handles streaming message requests, returning
    Server-Sent Events (SSE) with task updates.

    Args:
        request: The incoming HTTP request.

    Returns:
        SSE stream with task updates.
    """
    try:
        body = await request.json()

        # Extract order_id for metering
        order_id = _get_order_id_from_request(request)

        # Handle JSON-RPC format
        if "jsonrpc" in body:
            rpc_request = JSONRPCRequest(**body)
            if rpc_request.method == "message/stream":
                params = _preprocess_request_params(rpc_request.params)
                send_request = SendMessageRequest(**params)
            else:
                raise HTTPException(status_code=400, detail="Invalid method for streaming")
        else:
            body = _preprocess_request_params(body)
            send_request = SendMessageRequest(**body)

        # Start processing (non-blocking)
        task_id = str(uuid4())
        task = Task(
            id=task_id,
            context_id=send_request.message.context_id or str(uuid4()),
            status=TaskStatus(state=TaskState.submitted),
        )
        _tasks[task.id] = task

        # Start async processing with order_id for metering
        asyncio.create_task(
            _process_message_async(task, send_request.message, order_id=order_id)
        )

        return StreamingResponse(
            _stream_task_updates(task),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        logger.exception(f"Error handling streaming request: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def _process_message_async(
    task: Task,
    message: Message,
    order_id: str | None = None,
) -> None:
    """Process a message asynchronously and update the task.

    Args:
        task: The task to update.
        message: The message to process.
        order_id: Order ID for metering (optional).
    """
    try:
        task.status = TaskStatus(state=TaskState.working)
        _tasks[task.id] = task

        result_task = await _process_message(message, order_id=order_id)

        task.status = result_task.status
        task.artifacts = result_task.artifacts
        task.history = result_task.history
        _tasks[task.id] = task

    except Exception as e:
        task.status = TaskStatus(state=TaskState.failed)
        task.artifacts = [
            Artifact(
                artifact_id=str(uuid4()),
                parts=[TextPart(text=f"Error: {str(e)}")],
                name="error",
            )
        ]
        _tasks[task.id] = task


@router.get("/a2a/tasks/{task_id}")
async def get_task(task_id: str) -> JSONResponse:
    """Get task status by ID.

    Args:
        task_id: The task identifier.

    Returns:
        Task object with current status.
    """
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return JSONResponse(
        content=_tasks[task_id].model_dump(by_alias=True, exclude_none=True)
    )


@router.delete("/a2a/tasks/{task_id}")
async def cancel_task(task_id: str) -> JSONResponse:
    """Cancel a task by ID.

    Args:
        task_id: The task identifier.

    Returns:
        Cancellation confirmation.
    """
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    _tasks[task_id].status = TaskStatus(state=TaskState.canceled)
    return JSONResponse(content={"cancelled": True, "taskId": task_id})
