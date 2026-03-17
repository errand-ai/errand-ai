"""Task generator API routes."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database import get_session
from models import TaskGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task-generators", tags=["task-generators"])


async def _require_admin(request: Request):
    """Auth dependency — late import to avoid circular import with main.py."""
    from main import require_admin
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    security = HTTPBearer(auto_error=True)
    credentials = await security(request)
    return await require_admin(request, credentials)


class EmailGeneratorConfig(BaseModel):
    poll_interval: Optional[int] = Field(None, ge=60)
    task_prompt: Optional[str] = None


class EmailGeneratorUpdate(BaseModel):
    enabled: bool = False
    profile_id: Optional[str] = None
    config: Optional[EmailGeneratorConfig] = None


class TaskGeneratorResponse(BaseModel):
    id: str
    type: str
    enabled: bool
    profile_id: Optional[str]
    config: Optional[dict]
    created_at: str
    updated_at: str

    @staticmethod
    def from_model(tg: TaskGenerator) -> "TaskGeneratorResponse":
        return TaskGeneratorResponse(
            id=str(tg.id),
            type=tg.type,
            enabled=tg.enabled,
            profile_id=str(tg.profile_id) if tg.profile_id else None,
            config=tg.config,
            created_at=tg.created_at.isoformat() if tg.created_at else "",
            updated_at=tg.updated_at.isoformat() if tg.updated_at else "",
        )


@router.get("")
async def list_task_generators(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(select(TaskGenerator))
    generators = result.scalars().all()
    return [TaskGeneratorResponse.from_model(tg) for tg in generators]


@router.get("/email")
async def get_email_generator(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(
        select(TaskGenerator).where(TaskGenerator.type == "email")
    )
    tg = result.scalar_one_or_none()
    if not tg:
        raise HTTPException(status_code=404, detail="Email task generator not configured")
    return TaskGeneratorResponse.from_model(tg)


@router.put("/email")
async def upsert_email_generator(
    body: EmailGeneratorUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(
        select(TaskGenerator).where(TaskGenerator.type == "email")
    )
    tg = result.scalar_one_or_none()

    resolved_profile_id = None
    if body.profile_id:
        try:
            resolved_profile_id = uuid.UUID(body.profile_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid profile_id")

    config_dict = body.config.model_dump(exclude_none=True) if body.config else {}

    if tg:
        tg.enabled = body.enabled
        tg.profile_id = resolved_profile_id
        tg.config = config_dict
    else:
        tg = TaskGenerator(
            type="email",
            enabled=body.enabled,
            profile_id=resolved_profile_id,
            config=config_dict,
        )
        session.add(tg)

    await session.commit()
    await session.refresh(tg)
    return TaskGeneratorResponse.from_model(tg)
