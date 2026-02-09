import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import asyncio
import json
import logging

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import auth as auth_module
from auth import OIDCConfig
from auth_routes import router as auth_router
from database import engine, get_session
from events import init_valkey, close_valkey, publish_event, get_valkey, CHANNEL
from models import Setting, Task

security = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth_module.oidc = OIDCConfig.from_env()
    await auth_module.oidc.discover()
    await init_valkey()
    yield
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

VALID_STATUSES = ["new", "need-input", "scheduled", "pending", "running", "review", "completed"]


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    status: Optional[str] = None

    def model_post_init(self, __context):
        if self.status is not None and self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of: {', '.join(VALID_STATUSES)}")


class TaskResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Protected /api endpoints ---


@app.get("/api/tasks", response_model=list[TaskResponse])
async def list_tasks(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    result = await session.execute(select(Task).order_by(Task.created_at.desc()))
    return result.scalars().all()


@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    body: TaskCreate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    task = Task(title=body.title)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await publish_event("task_created", TaskResponse.model_validate(task).model_dump(mode="json"))
    return task


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.title is not None:
        task.title = body.title
    if body.status is not None:
        task.status = body.status
    await session.commit()
    await session.refresh(task)
    await publish_event("task_updated", TaskResponse.model_validate(task).model_dump(mode="json"))
    return task


# --- Admin settings endpoints ---


@app.get("/api/settings")
async def get_settings(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_admin),
):
    result = await session.execute(select(Setting))
    settings = result.scalars().all()
    return {s.key: s.value for s in settings}


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

logger = logging.getLogger(__name__)

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
