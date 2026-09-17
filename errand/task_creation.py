"""Turning resolved task fields into a task on the board.

Shared by `POST /api/tasks`, which classifies raw input first, and intake
(`clarify.confirm`), which already holds a spec the user agreed to. Posting a
confirmed spec back through `POST /api/tasks` would classify it again and
discard what the user confirmed, so both paths meet here instead.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from eval_marking import resolve_is_eval
from events import publish_event
from models import Tag, Task, task_tags
from utils import _next_position


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
    is_eval: bool = False
    # What became of classification for this task. Not persisted: it describes
    # how this creation went, not the task. Present so a caller can explain a
    # degraded classification instead of leaving the user to infer it from a
    # task that behaved oddly — `no_model_configured` in particular is a fault
    # in the installation, and the user cannot fix it by editing their words.
    classification: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_task(
        cls, task: Task, profile_name: str | None = None, classification: str | None = None
    ) -> "TaskResponse":
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
            classification=classification,
            is_eval=task.is_eval,
        )

async def sync_tags(session: AsyncSession, task: Task, tag_names: list[str]) -> None:
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

async def create_task_from_fields(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    category: str,
    execute_at: datetime | None,
    repeat_interval: str | None,
    repeat_until: datetime | None,
    profile_id: uuid.UUID | None,
    created_by: str | None,
    tag_names: list[str],
    classification: str | None = None,
) -> Task:
    """Create, route and announce a task; returns it with tags and profile loaded.

    Routing: a task tagged "Needs Info" goes to review, an immediate one to
    pending (with `execute_at` set to now), a scheduled or repeating one to
    scheduled. Commits.
    """
    if category == "immediate":
        execute_at = datetime.now(timezone.utc)

    task = Task(
        title=title,
        description=description,
        category=category,
        execute_at=execute_at,
        repeat_interval=repeat_interval,
        repeat_until=repeat_until,
        profile_id=profile_id,
        is_eval=await resolve_is_eval(session, profile_id),
        created_by=created_by,
    )
    session.add(task)
    await session.flush()

    if tag_names:
        await sync_tags(session, task, tag_names)

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
    resp = TaskResponse.from_task(
        task,
        profile_name=task.profile.name if task.profile else None,
        classification=classification,
    )
    await publish_event("task_created", resp.model_dump(mode="json"))
    return task
