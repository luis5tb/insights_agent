"""A2A protocol router with endpoints for agent communication."""

import asyncio
import logging
from collections.abc import AsyncGenerator
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

logger = logging.getLogger(__name__)

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


async def _process_message(message: Message) -> Task:
    """Process an incoming message and create a task.

    This is the core message handler that invokes the agent.

    Args:
        message: The incoming message to process.

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

        # For now, we'll use a simple response
        # In production, this would invoke the agent with the user message
        # The actual agent invocation depends on the ADK Runner API
        response_text = await _invoke_agent(agent, user_text, context_id)

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
            role="agent",
            parts=[TextPart(text=response_text)],
            context_id=context_id,
            task_id=task_id,
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


async def _invoke_agent(agent: Any, user_text: str, context_id: str) -> str:
    """Invoke the ADK agent with a user message.

    Args:
        agent: The ADK agent instance.
        user_text: User's message text.
        context_id: Conversation context ID.

    Returns:
        Agent's response text.
    """
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

        # Create or get session
        session = await session_service.create_session(
            app_name="insights-agent",
            user_id="a2a-user",
            session_id=context_id,
        )

        # Create user message content
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(user_text)],
        )

        # Run agent and collect response
        response_parts = []
        async for event in runner.run_async(
            session_id=session.id,
            user_id="a2a-user",
            new_message=user_content,
        ):
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)

        return "".join(response_parts) if response_parts else "No response generated."

    except ImportError:
        # Fallback if ADK runner is not available
        logger.warning("ADK Runner not available, using fallback response")
        return (
            f"I received your message: '{user_text[:100]}...'. "
            "The agent is configured but the full ADK runtime is not available. "
            "Please ensure google-adk is properly installed."
        )
    except Exception as e:
        logger.exception(f"Error invoking agent: {e}")
        return f"Error processing request: {str(e)}"


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

        # Handle JSON-RPC format
        if "jsonrpc" in body:
            rpc_request = JSONRPCRequest(**body)

            if rpc_request.method == "a2a.SendMessage":
                params = _preprocess_request_params(rpc_request.params)
                send_request = SendMessageRequest(**params)
                task = await _process_message(send_request.message)

                response = JSONRPCResponse(
                    result=SendMessageResponse(task=task).model_dump(by_alias=True),
                    id=rpc_request.id,
                )
                return JSONResponse(content=response.model_dump(by_alias=True, exclude_none=True))

            elif rpc_request.method == "a2a.GetTask":
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

            elif rpc_request.method == "a2a.CancelTask":
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
        task = await _process_message(send_request.message)

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

        # Handle JSON-RPC format
        if "jsonrpc" in body:
            rpc_request = JSONRPCRequest(**body)
            if rpc_request.method == "a2a.SendStreamingMessage":
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

        # Start async processing
        asyncio.create_task(_process_message_async(task, send_request.message))

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


async def _process_message_async(task: Task, message: Message) -> None:
    """Process a message asynchronously and update the task.

    Args:
        task: The task to update.
        message: The message to process.
    """
    try:
        task.status = TaskStatus(state=TaskState.working)
        _tasks[task.id] = task

        result_task = await _process_message(message)

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
