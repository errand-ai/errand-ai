import logging
import secrets
import uuid as uuid_mod

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl
from sqlalchemy import func, select
from starlette.applications import Starlette

from database import async_session
from events import publish_event
from llm import generate_title
from models import Setting, Task

logger = logging.getLogger(__name__)


class ApiKeyVerifier(TokenVerifier):
    """Validates Bearer token against the stored mcp_api_key setting."""

    async def verify_token(self, token: str) -> AccessToken | None:
        async with async_session() as session:
            result = await session.execute(
                select(Setting.value).where(Setting.key == "mcp_api_key")
            )
            stored_key = result.scalar_one_or_none()

        if stored_key is None:
            return None

        if not secrets.compare_digest(token, stored_key):
            return None

        return AccessToken(token=token, client_id="mcp-client", scopes=[])


mcp = FastMCP(
    "Content Manager",
    token_verifier=ApiKeyVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://localhost"),
        resource_server_url=AnyHttpUrl("https://localhost"),
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
async def new_task(description: str) -> str:
    """Create a new task from a description. Returns the task UUID."""
    async with async_session() as session:
        words = description.strip().split()

        category = "immediate"
        if len(words) > 5:
            llm_result = await generate_title(description, session)
            title = llm_result.title
            category = llm_result.category or "immediate"
        else:
            title = description.strip()

        # Auto-route based on category (same logic as main task creation)
        if category in ("scheduled", "repeating"):
            status = "scheduled"
        else:
            status = "pending"

        # Get next position for target status column
        result = await session.execute(
            select(func.max(Task.position)).where(Task.status == status)
        )
        max_pos = result.scalar()
        position = (max_pos or 0) + 1

        task = Task(
            title=title,
            description=description,
            category=category,
            status=status,
            position=position,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task, ["tags"])

        task_data = {
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "position": task.position,
            "category": task.category,
            "execute_at": None,
            "repeat_interval": None,
            "repeat_until": None,
            "output": None,
            "runner_logs": None,
            "retry_count": 0,
            "tags": [],
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
        await publish_event("task_created", task_data)

        return str(task.id)


@mcp.tool()
async def task_status(task_id: str) -> str:
    """Get the current status and details of a task by UUID."""
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == uuid_mod.UUID(task_id)))
        task = result.scalar_one_or_none()

        if task is None:
            return f"Error: Task {task_id} not found."

        return (
            f"Title: {task.title}\n"
            f"Status: {task.status}\n"
            f"Category: {task.category}\n"
            f"Created: {task.created_at.isoformat()}\n"
            f"Updated: {task.updated_at.isoformat()}"
        )


@mcp.tool()
async def task_output(task_id: str) -> str:
    """Get the output of a completed task by UUID."""
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == uuid_mod.UUID(task_id)))
        task = result.scalar_one_or_none()

        if task is None:
            return f"Error: Task {task_id} not found."

        if task.status in ("completed", "review"):
            return task.output or "(no output)"

        return f"Task is still in progress (status: {task.status})"


def create_mcp_app() -> Starlette:
    """Create the MCP Starlette app for mounting on the main FastAPI app.

    Also initializes mcp._session_manager as a side effect.
    The caller must run `mcp.session_manager.run()` in the app lifespan
    because Starlette 0.38.x does not propagate lifespans to mounted sub-apps.
    """
    return mcp.streamable_http_app()
