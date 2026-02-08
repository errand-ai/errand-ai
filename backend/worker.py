import asyncio
import logging
import os
import signal
from datetime import datetime, timezone

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session, engine
from models import Task

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))

shutdown_requested = False
shutdown_event: asyncio.Event | None = None


def handle_sigterm(*_args):
    global shutdown_requested
    logger.info("SIGTERM received, finishing current task before shutdown")
    shutdown_requested = True
    if shutdown_event is not None:
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(shutdown_event.set)


async def dequeue_task(session: AsyncSession) -> Task | None:
    result = await session.execute(
        select(Task)
        .where(Task.status == "pending")
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()


async def process_task(task: Task) -> None:
    logger.info("Processing task %s: %s", task.id, task.title)
    # MVP placeholder: simulate work
    await asyncio.sleep(2)


async def run() -> None:
    global shutdown_event
    shutdown_event = asyncio.Event()

    signal.signal(signal.SIGTERM, handle_sigterm)
    logger.info("Worker started, polling every %ds", POLL_INTERVAL)

    while not shutdown_requested:
        async with async_session() as session:
            task = await dequeue_task(session)
            if task is None:
                await session.close()
                if shutdown_requested:
                    break
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=POLL_INTERVAL)
                except TimeoutError:
                    pass
                continue

            # Set status to running
            task.status = "running"
            await session.commit()

        # Process outside the dequeue transaction
        try:
            await process_task(task)
            async with async_session() as session:
                await session.execute(
                    update(Task).where(Task.id == task.id).values(
                        status="completed", updated_at=datetime.now(timezone.utc)
                    )
                )
                await session.commit()
            logger.info("Task %s completed", task.id)
        except Exception:
            logger.exception("Task %s failed", task.id)
            async with async_session() as session:
                await session.execute(
                    update(Task).where(Task.id == task.id).values(
                        status="failed", updated_at=datetime.now(timezone.utc)
                    )
                )
                await session.commit()

    await engine.dispose()
    logger.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(run())
