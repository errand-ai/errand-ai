"""Shared tag helpers."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Tag, task_tags


async def add_tag(session: AsyncSession, task_id: uuid.UUID, tag_name: str) -> None:
    """Add a single tag to a task (find-or-create), ignoring if already associated."""
    result = await session.execute(select(Tag).where(Tag.name == tag_name))
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=tag_name)
        session.add(tag)
        await session.flush()

    # Check if association already exists
    existing = await session.execute(
        select(task_tags).where(
            task_tags.c.task_id == task_id,
            task_tags.c.tag_id == tag.id,
        )
    )
    if existing.first() is None:
        await session.execute(
            task_tags.insert().values(task_id=task_id, tag_id=tag.id)
        )
