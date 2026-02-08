import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import engine, get_session
from models import Task


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# --- Endpoints ---


@app.get("/api/tasks", response_model=list[TaskResponse])
async def list_tasks(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Task).order_by(Task.created_at.desc()))
    return result.scalars().all()


@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, session: AsyncSession = Depends(get_session)):
    task = Task(title=body.title)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/api/metrics/queue")
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
