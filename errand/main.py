import os
from pathlib import Path
import re
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
from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
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
from llm import init_llm_client, get_llm_client_with_db, generate_title, ProfileInfo, transcribe_audio, VALID_CATEGORIES, TranscriptionNotConfiguredError, LLMClientNotConfiguredError
from local_auth import router as local_auth_router
from models import LocalUser, PlatformCredential, Setting, Skill, SkillFile, Tag, Task, TaskProfile, task_tags
from settings_registry import EXCLUDED_KEYS, SETTINGS_REGISTRY, resolve_settings
from platforms import get_registry
from platforms.credentials import encrypt as encrypt_credentials, decrypt as decrypt_credentials
from mcp_server import create_mcp_app, mcp as mcp_server
from platforms.slack.routes import router as slack_router
from platforms.slack.status_updater import run_status_updater
from platforms.credentials import load_credentials as _load_creds
from email_poller import run_email_poller
from scheduler import run_scheduler, release_lock
from version_checker import run_version_checker, get_version_info
from zombie_cleanup import run_zombie_cleanup, release_zombie_lock

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
    return private_pem, f"{public_openssh} errand"


def _run_migrations():
    """Run Alembic migrations synchronously (called from a thread)."""
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command
    alembic_cfg = AlembicConfig(str(Path(__file__).resolve().parent / "alembic.ini"))
    alembic_command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run database migrations before anything else
    if os.environ.get("AUTO_MIGRATE", "").lower() in ("1", "true", "yes"):
        logger.info("AUTO_MIGRATE enabled — running Alembic migrations")
        await asyncio.to_thread(_run_migrations)
        logger.info("Migrations complete")

    # OIDC: try env vars first, then DB settings
    async with async_session() as session:
        db_settings = {}
        for key in ["oidc_discovery_url", "oidc_client_id", "oidc_client_secret", "oidc_roles_claim"]:
            result = await session.execute(select(Setting).where(Setting.key == key))
            s = result.scalar_one_or_none()
            if s:
                db_settings[key] = s.value
    oidc_config = OIDCConfig.from_env(db_settings)
    if oidc_config:
        try:
            await oidc_config.discover()
            auth_module.oidc = oidc_config
        except Exception:
            logger.error("OIDC discovery failed — starting without SSO", exc_info=True)
            auth_module.oidc = None
    else:
        auth_module.oidc = None
        logger.info("OIDC not configured — using local auth")
    await init_valkey()
    init_llm_client()

    # Credential encryption key — required for persistent credential storage
    if not os.environ.get("CREDENTIAL_ENCRYPTION_KEY"):
        logger.warning(
            "CREDENTIAL_ENCRYPTION_KEY not set — platform credential storage is disabled. "
            "Set this env var to enable saving platform credentials."
        )

    # Register platforms
    from platforms.twitter import TwitterPlatform
    from platforms.slack import SlackPlatform
    from platforms.github import GitHubPlatform
    from platforms.email import EmailPlatform
    from platforms.searxng import SearXNGPlatform
    registry = get_registry()
    registry.register(TwitterPlatform())
    registry.register(SlackPlatform())
    registry.register(GitHubPlatform())
    registry.register(EmailPlatform())
    registry.register(SearXNGPlatform())

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

        # Auto-generate JWT signing secret
        result = await session.execute(select(Setting).where(Setting.key == "jwt_signing_secret"))
        if result.scalar_one_or_none() is None:
            import secrets as _secrets
            session.add(Setting(key="jwt_signing_secret", value=_secrets.token_hex(32)))
            await session.commit()
            logger.info("Generated JWT signing secret")

        # Auto-provision local admin user from env vars
        admin_username = os.environ.get("ADMIN_USERNAME")
        admin_password = os.environ.get("ADMIN_PASSWORD")
        if admin_username and admin_password:
            from passlib.hash import bcrypt
            result = await session.execute(select(LocalUser).where(LocalUser.username == admin_username))
            if result.scalar_one_or_none() is None:
                session.add(LocalUser(username=admin_username, password_hash=bcrypt.hash(admin_password)))
                await session.commit()
                logger.info("Auto-provisioned local admin user '%s'", admin_username)

    scheduler_task = asyncio.create_task(run_scheduler())
    zombie_cleanup_task = asyncio.create_task(run_zombie_cleanup())
    slack_updater_task = asyncio.create_task(
        run_status_updater(get_valkey, async_session, _load_creds)
    )
    version_checker_task = asyncio.create_task(run_version_checker())
    email_poller_task = asyncio.create_task(run_email_poller())
    async with mcp_server.session_manager.run():
        yield
    scheduler_task.cancel()
    zombie_cleanup_task.cancel()
    slack_updater_task.cancel()
    version_checker_task.cancel()
    email_poller_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass  # Expected after explicit cancel()
    try:
        await zombie_cleanup_task
    except asyncio.CancelledError:
        pass  # Expected after explicit cancel()
    try:
        await slack_updater_task
    except asyncio.CancelledError:
        pass  # Expected after explicit cancel()
    try:
        await version_checker_task
    except asyncio.CancelledError:
        pass  # Expected after explicit cancel()
    try:
        await email_poller_task
    except asyncio.CancelledError:
        pass  # Expected after explicit cancel()
    await release_lock()
    await release_zombie_lock()
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
app.include_router(local_auth_router)
app.include_router(slack_router)

app.mount("/mcp", create_mcp_app())


@app.get("/api/version")
async def api_version():
    return get_version_info()


# --- Auth helpers ---


async def _resolve_auth_mode(session: AsyncSession) -> str:
    """Determine current auth mode: 'sso', 'local', or 'setup'."""
    # 1. OIDC env vars?
    if all(os.environ.get(v) for v in ["OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]):
        return "sso"
    # 2. OIDC DB settings?
    oidc_db_ok = True
    for key in ["oidc_discovery_url", "oidc_client_id", "oidc_client_secret"]:
        result = await session.execute(select(Setting).where(Setting.key == key))
        s = result.scalar_one_or_none()
        if not s or not s.value:
            oidc_db_ok = False
            break
    if oidc_db_ok:
        return "sso"
    # 3. Local user exists?
    result = await session.execute(select(LocalUser).limit(1))
    if result.scalar_one_or_none() is not None:
        return "local"
    # 4. Setup mode
    return "setup"


async def _validate_token(token: str) -> dict:
    """Validate a JWT token (OIDC or local). Returns claims dict with _roles."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    issuer = unverified.get("iss", "")

    if issuer == "errand-local":
        # Local token — verify with HMAC secret
        async with async_session() as db:
            result = await db.execute(
                select(Setting).where(Setting.key == "jwt_signing_secret")
            )
            secret_setting = result.scalar_one_or_none()
        if not secret_setting:
            raise HTTPException(status_code=401, detail="Local auth not configured")
        try:
            claims = jwt.decode(
                token, str(secret_setting.value), algorithms=["HS256"], issuer="errand-local"
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
        claims["_roles"] = claims.get("_roles", [])
        return claims
    else:
        # OIDC token
        if auth_module.oidc is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            claims = auth_module.oidc.decode_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
        roles = auth_module.oidc.extract_roles(claims)
        if not roles:
            raise HTTPException(status_code=403, detail="No roles assigned")
        claims["_roles"] = roles
        return claims


# --- Auth dependency ---


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return await _validate_token(credentials.credentials)


async def require_editor(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    claims = await _validate_token(credentials.credentials)
    roles = claims.get("_roles", [])
    if "editor" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Editor role required")
    return claims


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    claims = await _validate_token(credentials.credentials)
    roles = claims.get("_roles", [])
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


# --- Schemas ---

VALID_STATUSES = ["scheduled", "pending", "running", "review", "completed", "deleted", "archived"]


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
    profile_id: Optional[str] = Field(None, description="UUID of task profile, or null to clear")

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
    questions: Optional[list[str]] = None
    retry_count: int = 0
    heartbeat_at: Optional[datetime] = None
    profile_id: Optional[uuid.UUID] = None
    profile_name: Optional[str] = None
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_task(cls, task: Task, profile_name: str | None = None) -> "TaskResponse":
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
            questions=task.questions,
            retry_count=task.retry_count,
            heartbeat_at=task.heartbeat_at,
            profile_id=task.profile_id,
            profile_name=profile_name,
            tags=sorted([t.name for t in task.tags]),
            created_at=task.created_at,
            updated_at=task.updated_at,
            created_by=task.created_by,
            updated_by=task.updated_by,
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
        .options(selectinload(Task.tags), selectinload(Task.profile))
        .where(Task.status.not_in(["new", "deleted", "archived", "completed"]))
        .order_by(Task.position.asc(), Task.created_at.asc())
    )
    completed = await session.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.profile))
        .where(Task.status == "completed")
        .order_by(Task.updated_at.desc())
    )
    tasks = list(active.scalars().all()) + list(completed.scalars().all())
    return [TaskResponse.from_task(t, profile_name=t.profile.name if t.profile else None) for t in tasks]


@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    body: TaskCreate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_editor),
):
    input_text = body.input.strip()
    words = input_text.split()
    tag_names: list[str] = []
    resolved_profile_id = None

    if len(words) > 5:
        # Load profiles for LLM classification
        prof_result = await session.execute(select(TaskProfile).order_by(TaskProfile.name))
        db_profiles = prof_result.scalars().all()
        profile_infos = [ProfileInfo(name=p.name, match_rules=p.match_rules) for p in db_profiles] if db_profiles else None

        llm_result = await generate_title(input_text, session, now=datetime.now(timezone.utc), profiles=profile_infos)
        title = llm_result.title
        description = input_text
        category = llm_result.category
        execute_at_str = llm_result.execute_at
        repeat_interval = llm_result.repeat_interval
        repeat_until_str = llm_result.repeat_until
        if not llm_result.success:
            tag_names.append("Needs Info")

        # Resolve profile name to ID
        if llm_result.profile and db_profiles:
            profile_map = {p.name: p.id for p in db_profiles}
            resolved_profile_id = profile_map.get(llm_result.profile)
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
        profile_id=resolved_profile_id,
        created_by=_user.get("email"),
    )
    session.add(task)
    await session.flush()

    if tag_names:
        await _sync_tags(session, task, tag_names)

    # Auto-routing based on category and tags
    if "Needs Info" in tag_names:
        task.status = "review"
    elif category == "immediate":
        task.status = "pending"
    elif category in ("scheduled", "repeating"):
        task.status = "scheduled"

    # Assign position at the bottom of the target column
    task.position = await _next_position(session, task.status)

    await session.commit()
    await session.refresh(task, ["tags", "profile"])
    resp = TaskResponse.from_task(task, profile_name=task.profile.name if task.profile else None)
    await publish_event("task_created", resp.model_dump(mode="json"))
    return resp


@app.get("/api/tasks/archived", response_model=list[TaskResponse])
async def list_archived_tasks(
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_current_user),
):
    roles = claims.get("_roles", [])
    if "admin" in roles:
        status_filter = Task.status.in_(["deleted", "archived"])
    else:
        status_filter = Task.status == "archived"
    result = await session.execute(
        select(Task).options(selectinload(Task.tags), selectinload(Task.profile)).where(status_filter).order_by(Task.updated_at.desc())
    )
    tasks = result.scalars().all()
    return [TaskResponse.from_task(t, profile_name=t.profile.name if t.profile else None) for t in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    result = await session.execute(
        select(Task).options(selectinload(Task.tags), selectinload(Task.profile)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.from_task(task, profile_name=task.profile.name if task.profile else None)


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_editor),
):
    result = await session.execute(
        select(Task).options(selectinload(Task.tags), selectinload(Task.profile)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running":
        raise HTTPException(status_code=409, detail="Cannot edit a running task")
    task.updated_by = _user.get("email")
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
    if body.profile_id is not None:
        if body.profile_id == "null" or body.profile_id == "":
            task.profile_id = None
        else:
            try:
                pid = uuid.UUID(body.profile_id)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid profile_id format")
            # Validate FK exists
            prof = await session.execute(select(TaskProfile).where(TaskProfile.id == pid))
            if not prof.scalar_one_or_none():
                raise HTTPException(status_code=422, detail="Task profile not found")
            task.profile_id = pid

    await session.commit()
    await session.refresh(task, ["tags", "profile"])
    resp = TaskResponse.from_task(task, profile_name=task.profile.name if task.profile else None)
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
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    client = await get_llm_client_with_db(session)
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
    client = await get_llm_client_with_db(session)
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
    return await resolve_settings(session)


@app.put("/api/settings")
async def update_settings(
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    for key, value in body.items():
        if key == "skills":
            continue  # Skills managed via /api/skills
        if key in EXCLUDED_KEYS:
            continue
        # Check if this key is env-sourced (readonly)
        meta = SETTINGS_REGISTRY.get(key)
        if meta and meta["env_var"]:
            env_val = os.environ.get(meta["env_var"])
            if env_val is not None and env_val != "":
                continue  # Skip readonly env-sourced keys
        result = await session.execute(select(Setting).where(Setting.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            session.add(Setting(key=key, value=value))
    await session.commit()

    # Check if OIDC settings were updated — trigger hot-reload
    oidc_keys = {"oidc_discovery_url", "oidc_client_id", "oidc_client_secret", "oidc_roles_claim"}
    if oidc_keys.intersection(body.keys()):
        await _try_oidc_hot_reload(session)

    return await resolve_settings(session)


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


@app.get("/api/worker/defaults")
async def get_worker_defaults(_user: dict = Depends(require_admin)):
    """Return runtime defaults for worker settings (env vars not visible in settings UI)."""
    return {
        "max_turns": os.environ.get("MAX_TURNS", "") or None,
        "reasoning_effort": os.environ.get("REASONING_EFFORT", "") or None,
    }


# --- LiteLLM MCP discovery ---

LITELLM_SENSITIVE_FIELDS = {
    "env", "credentials", "command", "args", "static_headers",
    "authorization_url", "token_url", "registration_url", "extra_headers",
}


async def _resolve_openai_settings(session: AsyncSession) -> tuple[str, str]:
    """Resolve openai_base_url and openai_api_key: env var → DB → default."""
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if base_url and api_key:
        return base_url, api_key

    for key in ["openai_base_url", "openai_api_key"]:
        result = await session.execute(select(Setting).where(Setting.key == key))
        s = result.scalar_one_or_none()
        if s and s.value:
            if key == "openai_base_url" and not base_url:
                base_url = str(s.value)
            elif key == "openai_api_key" and not api_key:
                api_key = str(s.value)
    return base_url, api_key


@app.get("/api/litellm/mcp-servers")
async def get_litellm_mcp_servers(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    unavailable = {"available": False, "servers": {}, "enabled": []}

    base_url, api_key = await _resolve_openai_settings(session)
    if not base_url:
        return unavailable

    # Probe LiteLLM and fetch servers + tools in parallel
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            server_resp, tools_resp = await asyncio.gather(
                client.get(f"{base_url.rstrip('/')}/v1/mcp/server", headers=headers),
                client.get(f"{base_url.rstrip('/')}/v1/mcp/tools", headers=headers),
                return_exceptions=True,
            )
    except Exception:
        return unavailable

    # Check server response is valid
    if isinstance(server_resp, BaseException) or server_resp.status_code != 200:
        return unavailable
    try:
        server_list = server_resp.json()
        if not isinstance(server_list, list):
            return unavailable
    except Exception:
        return unavailable

    # Parse tools response (best-effort)
    tools_by_alias: dict[str, list[str]] = {}
    if not isinstance(tools_resp, BaseException) and tools_resp.status_code == 200:
        try:
            tools_list = tools_resp.json()
            if isinstance(tools_list, list):
                # Build set of known aliases for matching
                known_aliases = {
                    srv.get("alias", "") for srv in server_list if isinstance(srv, dict)
                }
                for tool in tools_list:
                    if not isinstance(tool, dict):
                        continue
                    tool_name = tool.get("name", "")
                    # Match prefix before first '-' against known aliases
                    dash_idx = tool_name.find("-")
                    if dash_idx > 0:
                        prefix = tool_name[:dash_idx]
                        if prefix in known_aliases:
                            short_name = tool_name[dash_idx + 1:]
                            tools_by_alias.setdefault(prefix, []).append(short_name)
                        else:
                            logger.warning("LiteLLM tool %s did not match any known server alias", tool_name)
        except Exception:
            pass  # Tools are best-effort

    # Build response: strip sensitive fields, add tools
    servers = {}
    for srv in server_list:
        if not isinstance(srv, dict):
            continue
        alias = srv.get("alias", "")
        if not alias:
            continue
        clean = {
            k: v for k, v in srv.items() if k not in LITELLM_SENSITIVE_FIELDS
        }
        clean["tools"] = tools_by_alias.get(alias, [])
        servers[alias] = clean

    # Read enabled servers from DB
    result = await session.execute(
        select(Setting).where(Setting.key == "litellm_mcp_servers")
    )
    setting = result.scalar_one_or_none()
    enabled = setting.value if setting and isinstance(setting.value, list) else []

    return {"available": True, "servers": servers, "enabled": enabled}


# --- Platform credential endpoints ---


@app.get("/api/platforms")
async def list_platforms(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    registry = get_registry()
    all_platforms = registry.list_all()

    # Load all credentials in one query
    result = await session.execute(select(PlatformCredential))
    creds_by_id = {c.platform_id: c for c in result.scalars().all()}

    platforms = []
    for info in all_platforms:
        cred = creds_by_id.get(info.id)
        platforms.append({
            "id": info.id,
            "label": info.label,
            "capabilities": sorted(info.capabilities),
            "credential_schema": info.credential_schema,
            "status": cred.status if cred else "disconnected",
            "last_verified_at": cred.last_verified_at.isoformat() if cred and cred.last_verified_at else None,
        })
    return platforms


@app.put("/api/platforms/{platform_id}/credentials")
async def save_platform_credentials(
    platform_id: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    registry = get_registry()
    platform = registry.get(platform_id)
    if platform is None:
        raise HTTPException(status_code=404, detail=f"Platform '{platform_id}' not found")

    try:
        verified = await platform.verify_credentials(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Credential verification failed: {exc}")
    if not verified:
        raise HTTPException(status_code=400, detail="Credential verification failed")

    now = datetime.now(timezone.utc)
    encrypted = encrypt_credentials(body)
    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.encrypted_data = encrypted
        existing.status = "connected"
        existing.last_verified_at = now
    else:
        session.add(PlatformCredential(
            platform_id=platform_id,
            encrypted_data=encrypted,
            status="connected",
            last_verified_at=now,
        ))
    await session.commit()
    return {
        "platform_id": platform_id,
        "status": "connected",
        "last_verified_at": now.isoformat(),
    }


@app.delete("/api/platforms/{platform_id}/credentials", status_code=204)
async def delete_platform_credentials(
    platform_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform_id)
    )
    cred = result.scalar_one_or_none()
    if cred is not None:
        await session.delete(cred)
        await session.commit()


@app.get("/api/platforms/{platform_id}/credentials")
async def get_platform_credential_status(
    platform_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    registry = get_registry()
    platform = registry.get(platform_id)
    if platform is None:
        raise HTTPException(status_code=404, detail=f"Platform '{platform_id}' not found")

    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform_id)
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        return {
            "platform_id": platform_id,
            "status": "disconnected",
            "last_verified_at": None,
            "configured_fields": [],
        }

    try:
        configured_fields = list(decrypt_credentials(cred.encrypted_data).keys())
    except Exception:
        logger.exception("Failed to decrypt credentials for platform '%s'", platform_id)
        return {
            "platform_id": platform_id,
            "status": "error",
            "last_verified_at": cred.last_verified_at.isoformat() if cred.last_verified_at else None,
            "configured_fields": [],
        }
    return {
        "platform_id": platform_id,
        "status": cred.status,
        "last_verified_at": cred.last_verified_at.isoformat() if cred.last_verified_at else None,
        "configured_fields": configured_fields,
    }


@app.post("/api/platforms/{platform_id}/credentials/verify")
async def verify_platform_credentials(
    platform_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    registry = get_registry()
    platform = registry.get(platform_id)
    if platform is None:
        raise HTTPException(status_code=404, detail=f"Platform '{platform_id}' not found")

    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform_id)
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=400, detail=f"No credentials configured for platform '{platform_id}'")

    try:
        credentials = decrypt_credentials(cred.encrypted_data)
    except Exception:
        logger.exception("Failed to decrypt credentials for platform '%s'", platform_id)
        cred.status = "error"
        await session.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to decrypt credentials for platform '{platform_id}'. They may need to be re-entered.",
        )
    verified = await platform.verify_credentials(credentials)
    now = datetime.now(timezone.utc)

    cred.status = "connected" if verified else "error"
    cred.last_verified_at = now
    await session.commit()

    return {
        "status": cred.status,
        "last_verified_at": now.isoformat(),
    }


# --- Skill validation helpers ---

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def validate_skill_name(name: str) -> str | None:
    """Validate skill name per Agent Skills rules. Returns error message or None."""
    if not name:
        return "Name is required"
    if len(name) > 64:
        return "Name must be at most 64 characters"
    if name != name.lower():
        return "Name must be lowercase"
    if "--" in name:
        return "Name must not contain consecutive hyphens"
    if not _SKILL_NAME_RE.match(name):
        return "Name must contain only lowercase letters, digits, and hyphens, and must not start or end with a hyphen"
    return None


_ALLOWED_SUBDIRS = {"scripts", "references", "assets"}


def validate_skill_file_path(path: str) -> str | None:
    """Validate skill file path. Returns error message or None."""
    if not path:
        return "Path is required"
    parts = path.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "Path must be one level deep within scripts/, references/, or assets/"
    if parts[0] not in _ALLOWED_SUBDIRS:
        return f"Path must be in one of: {', '.join(sorted(_ALLOWED_SUBDIRS))}/"
    return None




# --- Skills API ---


@app.get("/api/skills")
async def list_skills(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    result = await session.execute(
        select(Skill).options(selectinload(Skill.files)).order_by(Skill.name)
    )
    skills = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "instructions": s.instructions,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "files": [
                {"id": str(f.id), "path": f.path, "created_at": f.created_at.isoformat() if f.created_at else None}
                for f in s.files
            ],
        }
        for s in skills
    ]


@app.post("/api/skills", status_code=201)
async def create_skill(
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    name = body.get("name", "")
    description = body.get("description", "")
    instructions = body.get("instructions", "")

    name_error = validate_skill_name(name)
    if name_error:
        raise HTTPException(status_code=422, detail=name_error)

    if not description:
        raise HTTPException(status_code=422, detail="Description is required")
    if len(description) > 1024:
        raise HTTPException(status_code=422, detail="Description must be at most 1024 characters")

    if not instructions:
        raise HTTPException(status_code=422, detail="Instructions are required")

    # Check name uniqueness
    result = await session.execute(select(Skill).where(Skill.name == name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Skill with name '{name}' already exists")

    skill = Skill(name=name, description=description, instructions=instructions)
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.instructions,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
        "files": [],
    }


@app.get("/api/skills/{skill_id}")
async def get_skill_by_id(
    skill_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    result = await session.execute(
        select(Skill).where(Skill.id == skill_id).options(selectinload(Skill.files))
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.instructions,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
        "files": [
            {
                "id": str(f.id),
                "path": f.path,
                "content": f.content,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in skill.files
        ],
    }


@app.put("/api/skills/{skill_id}")
async def update_skill(
    skill_id: uuid.UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(
        select(Skill).where(Skill.id == skill_id).options(selectinload(Skill.files))
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    if "name" in body:
        name_error = validate_skill_name(body["name"])
        if name_error:
            raise HTTPException(status_code=422, detail=name_error)
        # Check uniqueness if name changed
        if body["name"] != skill.name:
            dup = await session.execute(select(Skill).where(Skill.name == body["name"]))
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=409, detail=f"Skill with name '{body['name']}' already exists")
        skill.name = body["name"]

    if "description" in body:
        if not body["description"]:
            raise HTTPException(status_code=422, detail="Description is required")
        if len(body["description"]) > 1024:
            raise HTTPException(status_code=422, detail="Description must be at most 1024 characters")
        skill.description = body["description"]

    if "instructions" in body:
        if not body["instructions"]:
            raise HTTPException(status_code=422, detail="Instructions are required")
        skill.instructions = body["instructions"]

    await session.commit()
    await session.refresh(skill)
    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.instructions,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
        "files": [
            {"id": str(f.id), "path": f.path, "created_at": f.created_at.isoformat() if f.created_at else None}
            for f in skill.files
        ],
    }


@app.delete("/api/skills/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await session.delete(skill)
    await session.commit()


@app.post("/api/skills/{skill_id}/files", status_code=201)
async def add_skill_file(
    skill_id: uuid.UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    path = body.get("path", "")
    content = body.get("content", "")

    path_error = validate_skill_file_path(path)
    if path_error:
        raise HTTPException(status_code=422, detail=path_error)

    if not content:
        raise HTTPException(status_code=422, detail="Content is required")

    # Check duplicate path
    dup = await session.execute(
        select(SkillFile).where(SkillFile.skill_id == skill_id, SkillFile.path == path)
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"File with path '{path}' already exists for this skill")

    skill_file = SkillFile(skill_id=skill.id, path=path, content=content)
    session.add(skill_file)
    await session.commit()
    await session.refresh(skill_file)
    return {
        "id": str(skill_file.id),
        "skill_id": str(skill_file.skill_id),
        "path": skill_file.path,
        "content": skill_file.content,
        "created_at": skill_file.created_at.isoformat() if skill_file.created_at else None,
    }


@app.delete("/api/skills/{skill_id}/files/{file_id}", status_code=204)
async def delete_skill_file(
    skill_id: uuid.UUID,
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(
        select(SkillFile).where(SkillFile.id == file_id, SkillFile.skill_id == skill_id)
    )
    skill_file = result.scalar_one_or_none()
    if not skill_file:
        raise HTTPException(status_code=404, detail="File not found")
    await session.delete(skill_file)
    await session.commit()


# --- Task Profiles CRUD ---

VALID_REASONING_EFFORTS = {"low", "medium", "high"}


def _profile_to_dict(p: TaskProfile) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "match_rules": p.match_rules,
        "model": p.model,
        "system_prompt": p.system_prompt,
        "max_turns": p.max_turns,
        "reasoning_effort": p.reasoning_effort,
        "mcp_servers": p.mcp_servers,
        "litellm_mcp_servers": p.litellm_mcp_servers,
        "skill_ids": p.skill_ids,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@app.get("/api/task-profiles")
async def list_task_profiles(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(TaskProfile).order_by(TaskProfile.name))
    profiles = result.scalars().all()
    return [_profile_to_dict(p) for p in profiles]


@app.post("/api/task-profiles", status_code=201)
async def create_task_profile(
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")

    reasoning_effort = body.get("reasoning_effort")
    if reasoning_effort is not None and reasoning_effort not in VALID_REASONING_EFFORTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid reasoning_effort '{reasoning_effort}'. Must be one of: {', '.join(sorted(VALID_REASONING_EFFORTS))}",
        )

    # Check name uniqueness
    result = await session.execute(select(TaskProfile).where(TaskProfile.name == name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Task profile with name '{name}' already exists")

    profile = TaskProfile(
        name=name,
        description=body.get("description"),
        match_rules=body.get("match_rules"),
        model=body.get("model"),
        system_prompt=body.get("system_prompt"),
        max_turns=body.get("max_turns"),
        reasoning_effort=reasoning_effort,
        mcp_servers=body.get("mcp_servers"),
        litellm_mcp_servers=body.get("litellm_mcp_servers"),
        skill_ids=body.get("skill_ids"),
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _profile_to_dict(profile)


@app.get("/api/task-profiles/{profile_id}")
async def get_task_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(TaskProfile).where(TaskProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Task profile not found")
    return _profile_to_dict(profile)


@app.put("/api/task-profiles/{profile_id}")
async def update_task_profile(
    profile_id: uuid.UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(TaskProfile).where(TaskProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Task profile not found")

    if "name" in body:
        name = (body["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name is required")
        # Check uniqueness if name changed
        if name != profile.name:
            dup = await session.execute(select(TaskProfile).where(TaskProfile.name == name))
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=409, detail=f"Task profile with name '{name}' already exists")
        profile.name = name

    if "reasoning_effort" in body:
        re_val = body["reasoning_effort"]
        if re_val is not None and re_val not in VALID_REASONING_EFFORTS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid reasoning_effort '{re_val}'. Must be one of: {', '.join(sorted(VALID_REASONING_EFFORTS))}",
            )
        profile.reasoning_effort = re_val

    for field in ("description", "match_rules", "model", "system_prompt", "max_turns", "mcp_servers", "litellm_mcp_servers", "skill_ids"):
        if field in body:
            setattr(profile, field, body[field])

    await session.commit()
    await session.refresh(profile)
    return _profile_to_dict(profile)


@app.delete("/api/task-profiles/{profile_id}", status_code=204)
async def delete_task_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(TaskProfile).where(TaskProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Task profile not found")
    await session.delete(profile)
    await session.commit()


# --- OIDC hot-reload ---


async def _try_oidc_hot_reload(session: AsyncSession):
    """Attempt to hot-reload OIDC config after settings change."""
    # Don't hot-reload if OIDC comes from env vars
    if all(os.environ.get(v) for v in ["OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]):
        return

    # Load DB settings
    db_settings = {}
    for key in ["oidc_discovery_url", "oidc_client_id", "oidc_client_secret", "oidc_roles_claim"]:
        result = await session.execute(select(Setting).where(Setting.key == key))
        s = result.scalar_one_or_none()
        if s:
            db_settings[key] = s.value

    new_config = OIDCConfig.from_env(db_settings)
    if new_config:
        try:
            await new_config.discover()
            auth_module.oidc = new_config
            logger.info("OIDC hot-reload successful")
        except Exception:
            logger.error("OIDC hot-reload failed", exc_info=True)
            raise HTTPException(
                status_code=400,
                detail="OIDC discovery failed — check the discovery URL",
            )
    else:
        auth_module.oidc = None
        logger.info("OIDC config removed — reverted to local auth")


# --- Auth status & Setup endpoints ---


@app.get("/api/auth/status")
async def auth_status(session: AsyncSession = Depends(get_session)):
    mode = await _resolve_auth_mode(session)
    result = {"mode": mode}
    if mode == "sso":
        result["login_url"] = "/auth/login"
    return result


@app.post("/api/setup/create-user")
async def setup_create_user(body: dict, session: AsyncSession = Depends(get_session)):
    # Check if any local user exists
    result = await session.execute(select(LocalUser).limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=403, detail="Setup already completed")

    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=422, detail="Username and password required")

    from passlib.hash import bcrypt

    user = LocalUser(username=username, password_hash=bcrypt.hash(password))
    session.add(user)
    await session.commit()

    # Generate JWT for auto-login
    jwt_result = await session.execute(
        select(Setting).where(Setting.key == "jwt_signing_secret")
    )
    secret_setting = jwt_result.scalar_one_or_none()
    if not secret_setting:
        raise HTTPException(status_code=500, detail="JWT signing secret not configured")

    from local_auth import _mint_local_jwt

    token = _mint_local_jwt(username, "admin", str(secret_setting.value))
    return {"access_token": token, "token_type": "bearer"}


# --- Unprotected endpoints ---


@app.get("/metrics/queue")
async def queue_metrics(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(func.count()).select_from(Task).where(Task.status == "pending")
    )
    return {"queue_depth": result.scalar()}



@app.post("/api/internal/task-result/{task_id}")
async def receive_task_result(task_id: str, request: Request):
    """Accept task-runner output via one-time Valkey token auth."""
    valkey = get_valkey()
    if valkey is None:
        raise HTTPException(status_code=503, detail="Valkey unavailable")

    # Read Bearer token from Authorization header
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    provided_token = auth_header[7:]

    # Validate against Valkey-stored token
    token_key = f"task_result_token:{task_id}"
    try:
        expected_token = await valkey.get(token_key)
    except Exception:
        raise HTTPException(status_code=503, detail="Valkey unavailable")

    if expected_token is None or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Token is valid — delete it (one-time use) and store the result
    try:
        await valkey.delete(token_key)
        body = await request.body()
        await valkey.set(f"task_result:{task_id}", body.decode("utf-8"), ex=600)
    except Exception:
        raise HTTPException(status_code=503, detail="Valkey unavailable")

    return {"ok": True}


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
        await _validate_token(token)
    except HTTPException:
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


@app.websocket("/api/ws/tasks/{task_id}/logs")
async def ws_task_logs(websocket: WebSocket, task_id: str, token: str = Query(default=None)):
    # Authenticate via query parameter
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        await _validate_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Check task exists and status
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        await websocket.close(code=4004, reason="Invalid task ID")
        return

    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_uuid))
        task = result.scalar_one_or_none()
        if task is None:
            await websocket.close(code=4004, reason="Task not found")
            return
        task_status = task.status

    await websocket.accept()

    # If not running, send end sentinel and close
    if task_status != "running":
        await websocket.send_json({"event": "task_log_end"})
        await websocket.close(code=1000)
        return

    valkey = get_valkey()
    if valkey is None:
        await websocket.close(code=1011, reason="Event bus unavailable")
        return

    log_channel = f"task_logs:{task_id}"
    pubsub = valkey.pubsub()
    await pubsub.subscribe(log_channel)

    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                data = msg["data"]
                await websocket.send_text(data)
                # Check for end sentinel
                try:
                    parsed = json.loads(data)
                    if parsed.get("event") == "task_log_end":
                        await websocket.close(code=1000)
                        return
                except (json.JSONDecodeError, TypeError):
                    pass  # Non-JSON messages are valid log lines, not an error
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.debug("WebSocket disconnected for task log stream %s", task_id)
    finally:
        await pubsub.unsubscribe(log_channel)
        await pubsub.aclose()


# --- Static file serving (production only) ---

STATIC_DIR = Path(__file__).resolve().parent / "static"

if STATIC_DIR.is_dir():
    _assets_dir = STATIC_DIR / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")

    @app.get("/{path:path}")
    async def spa_fallback(request: Request, path: str):
        static_root = STATIC_DIR.resolve()
        file_path = (STATIC_DIR / path).resolve()
        # Prevent path traversal outside static directory
        if path and file_path.is_relative_to(static_root) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(static_root / "index.html")
