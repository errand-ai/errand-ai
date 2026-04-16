"""Shared internal helpers for the errand server.

These utilities are consumed by multiple modules (main, task_manager, scheduler,
zombie_cleanup). Keep them minimal and dependency-light.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Task


async def _next_position(
    session: AsyncSession,
    status: str,
    exclude_id=None,
) -> int:
    """Return the next position value for a task in the given status column.

    Computes ``max(position) + 1`` across tasks with ``status == status``, or
    ``1`` when no such tasks exist. Pass ``exclude_id`` to ignore a specific
    task (used when recomputing a task's own position during a column move).
    """
    query = select(func.max(Task.position)).where(Task.status == status)
    if exclude_id is not None:
        query = query.where(Task.id != exclude_id)
    result = await session.execute(query)
    max_pos = result.scalar()
    return (max_pos or 0) + 1
