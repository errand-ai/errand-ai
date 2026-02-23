import asyncio
import logging
import os
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import async_session
from events import get_valkey, publish_event
from models import Task

logger = logging.getLogger(__name__)

ZOMBIE_TIMEOUT_SECONDS = int(os.environ.get("ZOMBIE_TIMEOUT_SECONDS", "300"))
ZOMBIE_CLEANUP_INTERVAL = int(os.environ.get("ZOMBIE_CLEANUP_INTERVAL", "60"))
ZOMBIE_LOCK_KEY = "errand:zombie-cleanup-lock"
ZOMBIE_LOCK_TTL = 30
MAX_RETRIES = 5


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


async def acquire_zombie_lock() -> bool:
    valkey = get_valkey()
    if valkey is None:
        return False
    lock_value = f"zombie-{socket.gethostname()}"
    result = await valkey.set(ZOMBIE_LOCK_KEY, lock_value, nx=True, ex=ZOMBIE_LOCK_TTL)
    if result:
        return True
    current = await valkey.get(ZOMBIE_LOCK_KEY)
    if current == lock_value:
        await valkey.expire(ZOMBIE_LOCK_KEY, ZOMBIE_LOCK_TTL)
        return True
    return False


async def refresh_zombie_lock() -> bool:
    valkey = get_valkey()
    if valkey is None:
        return False
    return await valkey.expire(ZOMBIE_LOCK_KEY, ZOMBIE_LOCK_TTL)


async def release_zombie_lock() -> None:
    valkey = get_valkey()
    if valkey is None:
        return
    try:
        await valkey.delete(ZOMBIE_LOCK_KEY)
    except Exception:
        logger.warning("Failed to release zombie cleanup lock", exc_info=True)


async def _next_position(session: AsyncSession, status: str) -> int:
    result = await session.execute(
        select(func.max(Task.position)).where(Task.status == status)
    )
    max_pos = result.scalar()
    return (max_pos or 0) + 1


async def recover_zombie_tasks() -> int:
    """Detect and recover tasks stuck in running state with stale heartbeats."""
    recovered = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=ZOMBIE_TIMEOUT_SECONDS)

    async with async_session() as session:
        # Find running tasks with stale heartbeat OR null heartbeat with stale updated_at
        from sqlalchemy import or_, and_
        stmt = (
            select(Task)
            .options(selectinload(Task.tags))
            .where(
                Task.status == "running",
                or_(
                    and_(Task.heartbeat_at.isnot(None), Task.heartbeat_at < cutoff),
                    and_(Task.heartbeat_at.is_(None), Task.updated_at < cutoff),
                ),
            )
        )
        result = await session.execute(stmt)
        stale_tasks = result.scalars().all()

        for task in stale_tasks:
            stale_since = task.heartbeat_at or task.updated_at
            if stale_since:
                # Ensure timezone-aware for subtraction (SQLite returns naive datetimes)
                if stale_since.tzinfo is None:
                    stale_since = stale_since.replace(tzinfo=timezone.utc)
                stale_duration = (now - stale_since).total_seconds()
            else:
                stale_duration = 0

            if task.retry_count >= MAX_RETRIES:
                # Exhausted retries — move to review
                task.status = "review"
                task.position = await _next_position(session, "review")
                task.output = (
                    f"Task recovered from zombie state after {int(stale_duration)}s without heartbeat. "
                    f"Retry count ({task.retry_count}) has reached the maximum ({MAX_RETRIES}). "
                    "Moved to review for manual inspection."
                )
                task.updated_by = "system"
                task.updated_at = now
                task.heartbeat_at = None
                logger.info(
                    "Zombie task %s moved to review (retries exhausted, stale for %ds)",
                    task.id, int(stale_duration),
                )
            else:
                # Retry with exponential backoff
                backoff_minutes = 2 ** task.retry_count  # 1, 2, 4, 8, 16, ...
                execute_at = now + timedelta(minutes=backoff_minutes)
                task.status = "scheduled"
                task.position = await _next_position(session, "scheduled")
                task.retry_count += 1
                task.execute_at = execute_at
                task.updated_by = "system"
                task.updated_at = now
                task.heartbeat_at = None
                logger.info(
                    "Zombie task %s recovered to scheduled (retry %d, stale for %ds, backoff %dm)",
                    task.id, task.retry_count, int(stale_duration), backoff_minutes,
                )

            recovered += 1

        if stale_tasks:
            await session.commit()
            for task in stale_tasks:
                await session.refresh(task, ["tags"])
                await publish_event("task_updated", _task_to_dict(task))

    return recovered


async def run_zombie_cleanup() -> None:
    logger.info(
        "Zombie cleanup started (interval=%ds, timeout=%ds)",
        ZOMBIE_CLEANUP_INTERVAL, ZOMBIE_TIMEOUT_SECONDS,
    )
    while True:
        try:
            locked = await acquire_zombie_lock()
            if locked:
                count = await recover_zombie_tasks()
                if count:
                    logger.info("Recovered %d zombie task(s)", count)
                await refresh_zombie_lock()
            else:
                logger.debug("Zombie cleanup lock held by another replica, skipping cycle")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Zombie cleanup cycle error", exc_info=True)

        try:
            await asyncio.sleep(ZOMBIE_CLEANUP_INTERVAL)
        except asyncio.CancelledError:
            break

    await release_zombie_lock()
    logger.info("Zombie cleanup stopped")
