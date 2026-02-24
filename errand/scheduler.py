import asyncio
import logging
import os
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import async_session
from events import get_valkey, publish_event
from models import Setting, Task

logger = logging.getLogger(__name__)

SCHEDULER_INTERVAL = int(os.environ.get("SCHEDULER_INTERVAL", "15"))
LOCK_KEY = "errand:scheduler-lock"
LOCK_TTL = 30
BATCH_SIZE = 100


def _task_to_dict(task: Task) -> dict:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "position": task.position,
        "category": task.category,
        "execute_at": task.execute_at.isoformat() if task.execute_at else None,
        "repeat_interval": task.repeat_interval,
        "repeat_until": task.repeat_until.isoformat() if task.repeat_until else None,
        "output": task.output,
        "retry_count": task.retry_count,
        "heartbeat_at": task.heartbeat_at.isoformat() if task.heartbeat_at else None,
        "tags": sorted([t.name for t in task.tags]),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


async def _next_position(session: AsyncSession, status: str) -> int:
    result = await session.execute(
        select(func.max(Task.position)).where(Task.status == status)
    )
    max_pos = result.scalar()
    return (max_pos or 0) + 1


async def acquire_lock() -> bool:
    valkey = get_valkey()
    if valkey is None:
        return False
    lock_value = socket.gethostname()
    # Try to create lock (only if not exists)
    result = await valkey.set(LOCK_KEY, lock_value, nx=True, ex=LOCK_TTL)
    if result:
        return True
    # If we already hold the lock, refresh and continue
    current = await valkey.get(LOCK_KEY)
    if current == lock_value:
        await valkey.expire(LOCK_KEY, LOCK_TTL)
        return True
    return False


async def refresh_lock() -> bool:
    valkey = get_valkey()
    if valkey is None:
        return False
    return await valkey.expire(LOCK_KEY, LOCK_TTL)


async def release_lock() -> None:
    valkey = get_valkey()
    if valkey is None:
        return
    try:
        await valkey.delete(LOCK_KEY)
    except Exception:
        logger.warning("Failed to release scheduler lock", exc_info=True)


async def promote_due_tasks() -> int:
    promoted = 0
    async with async_session() as session:
        stmt = (
            select(Task)
            .options(selectinload(Task.tags))
            .where(Task.status == "scheduled", Task.execute_at <= func.now())
            .order_by(Task.execute_at)
            .limit(BATCH_SIZE)
        )
        dialect = session.bind.dialect.name
        if dialect != "sqlite":
            stmt = stmt.with_for_update(skip_locked=True)
        result = await session.execute(stmt)
        tasks = result.scalars().all()

        for task in tasks:
            position = await _next_position(session, "pending")
            task.status = "pending"
            task.position = position
            task.updated_at = datetime.now(timezone.utc)
            promoted += 1

        if tasks:
            await session.commit()
            for task in tasks:
                await session.refresh(task, ["tags"])
                await publish_event("task_updated", _task_to_dict(task))

    return promoted


async def archive_completed_tasks() -> int:
    archived = 0
    async with async_session() as session:
        # Read archive_after_days setting (default 3)
        result = await session.execute(
            select(Setting).where(Setting.key == "archive_after_days")
        )
        setting = result.scalar_one_or_none()
        archive_after_days = int(setting.value) if setting else 3

        cutoff = datetime.now(timezone.utc) - timedelta(days=archive_after_days)
        stmt = (
            select(Task)
            .options(selectinload(Task.tags))
            .where(Task.status == "completed", Task.updated_at < cutoff)
            .limit(BATCH_SIZE)
        )
        result = await session.execute(stmt)
        tasks = result.scalars().all()

        for task in tasks:
            task.status = "archived"
            task.updated_at = datetime.now(timezone.utc)
            archived += 1

        if tasks:
            await session.commit()
            for task in tasks:
                await session.refresh(task, ["tags"])
                await publish_event("task_updated", _task_to_dict(task))

    return archived


async def run_scheduler() -> None:
    logger.info("Scheduler started (interval=%ds)", SCHEDULER_INTERVAL)
    while True:
        try:
            locked = await acquire_lock()
            if locked:
                count = await promote_due_tasks()
                if count:
                    logger.info("Promoted %d scheduled task(s) to pending", count)
                archived = await archive_completed_tasks()
                if archived:
                    logger.info("Archived %d completed task(s)", archived)
                await refresh_lock()
            else:
                logger.debug("Scheduler lock held by another replica, skipping cycle")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Scheduler cycle error", exc_info=True)

        try:
            await asyncio.sleep(SCHEDULER_INTERVAL)
        except asyncio.CancelledError:
            break

    await release_lock()
    logger.info("Scheduler stopped")
