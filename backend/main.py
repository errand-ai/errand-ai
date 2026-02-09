import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import auth as auth_module
from auth import OIDCConfig
from auth_routes import router as auth_router
from database import engine, get_session
from models import Task

security = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth_module.oidc = OIDCConfig.from_env()
    await auth_module.oidc.discover()
    yield
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


# --- Schemas ---


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)


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
