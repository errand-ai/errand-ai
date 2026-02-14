import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncio
import json
import logging

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

import jwt
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import auth as auth_module
from auth import OIDCConfig
from auth_routes import router as auth_router
from database import async_session, engine, get_session
from events import init_valkey, close_valkey, publish_event, get_valkey, CHANNEL
from llm import init_llm_client, get_llm_client, generate_title, transcribe_audio, LLMResult, VALID_CATEGORIES, TranscriptionNotConfiguredError, LLMClientNotConfiguredError
from models import Setting, Tag, Task, task_tags
from mcp_server import create_mcp_app, mcp as mcp_server
from scheduler import run_scheduler, release_lock

security = HTTPBearer()


def generate_ssh_keypair() -> tuple[str, str]:
    """Generate an Ed25519 SSH keypair. Returns (private_key_pem, public_key_openssh)."""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_openssh = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")
    return private_pem, f"{public_openssh} content-manager"


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth_module.oidc = OIDCConfig.from_env()
    await auth_module.oidc.discover()
    await init_valkey()
    init_llm_client()

    # Auto-generate MCP API key and default system prompt if they don't exist
    async with async_session() as session:
        result = await session.execute(select(Setting).where(Setting.key == "mcp_api_key"))
        if result.scalar_one_or_none() is None:
            session.add(Setting(key="mcp_api_key", value=secrets.token_hex(32)))
            await session.commit()
            logger.info("Generated new MCP API key")

        result = await session.execute(select(Setting).where(Setting.key == "system_prompt"))
        if result.scalar_one_or_none() is None:
            default_prompt = (
                "You are a helpful personal assistant. When you are asked to perform a task, "
                "carry it out to the best of your ability.\n"
                "\n"
                "RULES:\n"
                "- Verify your results before you finish. Make sure that you have addressed "
                "all the requirements and not missed any.\n"
                "- If you need clarification on an issue that is preventing you from completing "
                "the task, ask the user specific targeted questions that will provide the "
                "clarification needed to complete the task."
            )
            session.add(Setting(key="system_prompt", value=default_prompt))
            await session.commit()
            logger.info("Created default system prompt")

        result = await session.execute(select(Setting).where(Setting.key == "ssh_private_key"))
        if result.scalar_one_or_none() is None:
            private_pem, public_openssh = generate_ssh_keypair()
            session.add(Setting(key="ssh_private_key", value=private_pem))
            session.add(Setting(key="ssh_public_key", value=public_openssh))
            await session.commit()
            logger.info("Generated new SSH keypair")

        result = await session.execute(select(Setting).where(Setting.key == "git_ssh_hosts"))
        if result.scalar_one_or_none() is None:
            session.add(Setting(key="git_ssh_hosts", value=["github.com", "bitbucket.org"]))
            await session.commit()
            logger.info("Created default git SSH hosts")

    scheduler_task = asyncio.create_task(run_scheduler())
    async with mcp_server.session_manager.run():
        yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await release_lock()
    await close_valkey()
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.mount("/mcp", create_mcp_app())


# --- Auth dependency ---


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        claims = auth_module.oidc.decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    roles = auth_module.oidc.extract_roles(claims)
    if not roles:
        raise HTTPException(
            status_code=403,
            detail="No roles assigned. Contact your administrator for access.",
        )

    return claims


async def require_editor(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        claims = auth_module.oidc.decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    roles = auth_module.oidc.extract_roles(claims)
    if "editor" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Editor role required")

    return claims


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        claims = auth_module.oidc.decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    roles = auth_module.oidc.extract_roles(claims)
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required")

    return claims


# --- Schemas ---

VALID_STATUSES = ["new", "scheduled", "pending", "running", "review", "completed", "deleted", "archived"]


class TaskCreate(BaseModel):
    input: str = Field(..., min_length=1)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    status: Optional[str] = None
    position: Optional[int] = None
    tags: Optional[list[str]] = None
    category: Optional[str] = None
    execute_at: Optional[str] = None
    repeat_interval: Optional[str] = None
    repeat_until: Optional[str] = None
    output: Optional[str] = None

    def model_post_init(self, __context):
        if self.status is not None and self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of: {', '.join(VALID_STATUSES)}")
        if self.category is not None and self.category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category '{self.category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}")


class TaskResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    status: str
    position: int = 0
    category: Optional[str] = None
    execute_at: Optional[datetime] = None
    repeat_interval: Optional[str] = None
    repeat_until: Optional[datetime] = None
    output: Optional[str] = None
    runner_logs: Optional[str] = None
    retry_count: int = 0
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_task(cls, task: Task) -> "TaskResponse":
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            position=task.position,
            category=task.category,
            execute_at=task.execute_at,
            repeat_interval=task.repeat_interval,
            repeat_until=task.repeat_until,
            output=task.output,
            runner_logs=task.runner_logs,
            retry_count=task.retry_count,
            tags=sorted([t.name for t in task.tags]),
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class TagResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


# --- Protected /api endpoints ---


async def _next_position(session: AsyncSession, status: str, exclude_id=None) -> int:
    """Return the next position value for a task in the given status column."""
    query = select(func.max(Task.position)).where(Task.status == status)
    if exclude_id is not None:
        query = query.where(Task.id != exclude_id)
    result = await session.execute(query)
    max_pos = result.scalar()
    return (max_pos or 0) + 1


@app.get("/api/tags", response_model=list[TagResponse])
async def list_tags(
    q: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    query = select(Tag)
    if q:
        query = query.where(Tag.name.ilike(f"{q}%"))
    query = query.order_by(Tag.name).limit(10)
    result = await session.execute(query)
    return result.scalars().all()


async def _sync_tags(session: AsyncSession, task: Task, tag_names: list[str]) -> None:
    """Replace task's tags with the given names, creating any that don't exist."""
    # Clear existing associations
    await session.execute(delete(task_tags).where(task_tags.c.task_id == task.id))

    if not tag_names:
        return

    # Find or create tags, then insert associations directly
    for name in tag_names:
        result = await session.execute(select(Tag).where(Tag.name == name))
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            await session.flush()
        await session.execute(
            task_tags.insert().values(task_id=task.id, tag_id=tag.id)
        )


@app.get("/api/tasks", response_model=list[TaskResponse])
async def list_tasks(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    # Completed tasks: most recently completed first (updated_at DESC)
    # All other columns: position ASC, created_at ASC
    active = await session.execute(
        select(Task)
        .options(selectinload(Task.tags))
        .where(Task.status.not_in(["deleted", "archived", "completed"]))
        .order_by(Task.position.asc(), Task.created_at.asc())
    )
    completed = await session.execute(
        select(Task)
        .options(selectinload(Task.tags))
        .where(Task.status == "completed")
        .order_by(Task.updated_at.desc())
    )
    tasks = list(active.scalars().all()) + list(completed.scalars().all())
    return [TaskResponse.from_task(t) for t in tasks]


@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    body: TaskCreate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_editor),
):
    input_text = body.input.strip()
    words = input_text.split()
    tag_names: list[str] = []

    if len(words) > 5:
        llm_result = await generate_title(input_text, session, now=datetime.now(timezone.utc))
        title = llm_result.title
        description = input_text
        category = llm_result.category
        execute_at_str = llm_result.execute_at
        repeat_interval = llm_result.repeat_interval
        repeat_until_str = llm_result.repeat_until
        if not llm_result.success:
            tag_names.append("Needs Info")
    else:
        title = input_text
        description = None
        category = "immediate"
        execute_at_str = None
        repeat_interval = None
        repeat_until_str = None
        tag_names.append("Needs Info")

    # Parse datetime strings from LLM
    execute_at = None
    if execute_at_str:
        try:
            execute_at = datetime.fromisoformat(execute_at_str)
        except (ValueError, TypeError):
            pass

    repeat_until = None
    if repeat_until_str:
        try:
            repeat_until = datetime.fromisoformat(repeat_until_str)
        except (ValueError, TypeError):
            pass

    # For immediate tasks, backend sets execute_at to current server time
    if category == "immediate":
        execute_at = datetime.now(timezone.utc)

    task = Task(
        title=title,
        description=description,
        category=category,
        execute_at=execute_at,
        repeat_interval=repeat_interval,
        repeat_until=repeat_until,
    )
    session.add(task)
    await session.flush()

    if tag_names:
        await _sync_tags(session, task, tag_names)

    # Auto-routing: if no "Needs Info" tag, route based on category
    if "Needs Info" not in tag_names:
        if category == "immediate":
            task.status = "pending"
        elif category in ("scheduled", "repeating"):
            task.status = "scheduled"

    # Assign position at the bottom of the target column
    task.position = await _next_position(session, task.status)

    await session.commit()
    await session.refresh(task, ["tags"])
    resp = TaskResponse.from_task(task)
    await publish_event("task_created", resp.model_dump(mode="json"))
    return resp


@app.get("/api/tasks/archived", response_model=list[TaskResponse])
async def list_archived_tasks(
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_current_user),
):
    roles = claims.get("resource_access", {}).get("content-manager", {}).get("roles", [])
    if "admin" in roles:
        status_filter = Task.status.in_(["deleted", "archived"])
    else:
        status_filter = Task.status == "archived"
    result = await session.execute(
        select(Task).options(selectinload(Task.tags)).where(status_filter).order_by(Task.updated_at.desc())
    )
    tasks = result.scalars().all()
    return [TaskResponse.from_task(t) for t in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    result = await session.execute(
        select(Task).options(selectinload(Task.tags)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.from_task(task)


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_editor),
):
    result = await session.execute(
        select(Task).options(selectinload(Task.tags)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running":
        raise HTTPException(status_code=409, detail="Cannot edit a running task")
    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description

    status_changed = body.status is not None and body.status != task.status
    if body.status is not None:
        task.status = body.status

    if status_changed:
        # Moving to a new column — assign bottom position (exclude self from max query)
        task.position = await _next_position(session, task.status, exclude_id=task.id)
    elif body.position is not None and body.position != task.position:
        # Intra-column reorder: shift other tasks to make room
        new_pos = body.position
        old_pos = task.position
        if new_pos < old_pos:
            # Moving up: shift tasks in [new_pos, old_pos) down by 1
            await session.execute(
                update(Task)
                .where(Task.status == task.status, Task.position >= new_pos, Task.position < old_pos, Task.id != task.id)
                .values(position=Task.position + 1)
            )
        else:
            # Moving down: shift tasks in (old_pos, new_pos] up by 1
            await session.execute(
                update(Task)
                .where(Task.status == task.status, Task.position > old_pos, Task.position <= new_pos, Task.id != task.id)
                .values(position=Task.position - 1)
            )
        task.position = new_pos

    if body.output is not None:
        task.output = body.output
    if body.category is not None:
        task.category = body.category
    if body.execute_at is not None:
        try:
            task.execute_at = datetime.fromisoformat(body.execute_at)
        except (ValueError, TypeError):
            task.execute_at = None
    if body.repeat_interval is not None:
        task.repeat_interval = body.repeat_interval
    if body.repeat_until is not None:
        try:
            task.repeat_until = datetime.fromisoformat(body.repeat_until)
        except (ValueError, TypeError):
            task.repeat_until = None
    if body.tags is not None:
        await _sync_tags(session, task, body.tags)

    # Auto-promotion: new + "Needs Info" + description + scheduling → scheduled
    has_needs_info = any(t.name == "Needs Info" for t in task.tags)
    if (
        task.status == "new"
        and has_needs_info
        and body.description is not None
        and body.description.strip()
        and (body.execute_at is not None or body.repeat_interval is not None)
    ):
        task.status = "scheduled"
        # Remove "Needs Info" tag
        current_tags = [t.name for t in task.tags if t.name != "Needs Info"]
        await _sync_tags(session, task, current_tags)

    await session.commit()
    await session.refresh(task, ["tags"])
    resp = TaskResponse.from_task(task)
    await publish_event("task_updated", resp.model_dump(mode="json"))
    return resp


@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_editor),
):
    result = await session.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "deleted"
    await session.commit()
    await publish_event("task_deleted", {"id": str(task.id)})


# --- LLM endpoints ---


@app.get("/api/llm/models")
async def list_llm_models(
    _user: dict = Depends(require_admin),
):
    client = get_llm_client()
    if client is None:
        raise HTTPException(status_code=503, detail="LLM provider not configured")
    try:
        models = await client.models.list()
        model_ids = sorted([m.id for m in models.data])
        return model_ids
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch models from LLM provider")


# --- Transcription endpoints ---


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    try:
        text = await transcribe_audio(file, session)
        return {"text": text}
    except (TranscriptionNotConfiguredError, LLMClientNotConfiguredError):
        raise HTTPException(status_code=503, detail="Transcription not configured")
    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=502, detail="Transcription failed")


@app.get("/api/transcribe/status")
async def transcribe_status(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    client = get_llm_client()
    if client is None:
        return {"enabled": False}
    result = await session.execute(select(Setting).where(Setting.key == "transcription_model"))
    setting = result.scalar_one_or_none()
    enabled = setting is not None and bool(setting.value)
    return {"enabled": enabled}


@app.get("/api/llm/transcription-models")
async def list_transcription_models(
    _user: dict = Depends(require_admin),
):
    base_url = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    api_key = os.environ.get("OPENAI_API_KEY", "")
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{base_url}/model/info",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        models = []
        for entry in data.get("data", []):
            if entry.get("model_info", {}).get("mode") == "audio_transcription":
                models.append(entry["model_name"])
        return sorted(models)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch model info from LLM provider")


# --- Admin settings endpoints ---


@app.get("/api/settings")
async def get_settings(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(Setting))
    settings = result.scalars().all()
    data = {s.key: s.value for s in settings if s.key != "ssh_private_key"}
    # Ensure skills always present (default to empty array)
    if "skills" not in data:
        data["skills"] = []
    return data


@app.put("/api/settings")
async def update_settings(
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    for key, value in body.items():
        result = await session.execute(select(Setting).where(Setting.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            session.add(Setting(key=key, value=value))
    await session.commit()

    result = await session.execute(select(Setting))
    settings = result.scalars().all()
    return {s.key: s.value for s in settings}


@app.post("/api/settings/regenerate-ssh-key")
async def regenerate_ssh_key(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    private_pem, public_openssh = generate_ssh_keypair()
    for key, value in [("ssh_private_key", private_pem), ("ssh_public_key", public_openssh)]:
        result = await session.execute(select(Setting).where(Setting.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            session.add(Setting(key=key, value=value))
    await session.commit()
    return {"ssh_public_key": public_openssh}


@app.post("/api/settings/regenerate-mcp-key")
async def regenerate_mcp_key(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    new_key = secrets.token_hex(32)
    result = await session.execute(select(Setting).where(Setting.key == "mcp_api_key"))
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = new_key
    else:
        session.add(Setting(key="mcp_api_key", value=new_key))
    await session.commit()
    return {"mcp_api_key": new_key}


# --- Unprotected endpoints ---


@app.get("/metrics/queue")
async def queue_metrics(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(func.count()).select_from(Task).where(Task.status == "pending")
    )
    return {"queue_depth": result.scalar()}


@app.get("/api/health")
async def health(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unreachable")


# --- WebSocket endpoint ---

PING_INTERVAL = 30
PONG_TIMEOUT = 10


@app.websocket("/api/ws/tasks")
async def ws_tasks(websocket: WebSocket, token: str = Query(default=None)):
    # Authenticate via query parameter
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        claims = auth_module.oidc.decode_token(token)
        roles = auth_module.oidc.extract_roles(claims)
        if not roles:
            await websocket.close(code=4001, reason="No roles")
            return
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    valkey = get_valkey()
    if valkey is None:
        await websocket.close(code=1011, reason="Event bus unavailable")
        return

    pubsub = valkey.pubsub()
    await pubsub.subscribe(CHANNEL)

    async def forward_events():
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    await websocket.send_text(msg["data"])
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    async def keepalive():
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)
                await websocket.send_json({"event": "ping"})
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    forward_task = asyncio.create_task(forward_events())
    ping_task = asyncio.create_task(keepalive())

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        ping_task.cancel()
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.aclose()
