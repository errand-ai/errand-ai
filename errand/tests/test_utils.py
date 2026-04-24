"""Tests for ``errand/utils.py`` shared helpers."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from models import Task
from utils import _next_position


_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'review' NOT NULL,
    category TEXT DEFAULT 'immediate',
    execute_at DATETIME,
    repeat_interval TEXT,
    repeat_until DATETIME,
    position INTEGER DEFAULT 0 NOT NULL,
    output TEXT,
    runner_logs TEXT,
    questions TEXT,
    retry_count INTEGER DEFAULT 0 NOT NULL,
    heartbeat_at DATETIME,
    profile_id VARCHAR(36),
    created_by TEXT,
    updated_by TEXT,
        encrypted_env TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture()
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_TASKS_SQL))
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_next_position_no_tasks(session: AsyncSession):
    """No existing tasks for the status returns 1."""
    assert await _next_position(session, "pending") == 1


async def test_next_position_increments_max(session: AsyncSession):
    """Returns max(position) + 1 among tasks in the given status."""
    for pos in (1, 3, 5):
        session.add(Task(id=uuid.uuid4(), title=f"t{pos}", status="pending", position=pos))
    await session.commit()

    assert await _next_position(session, "pending") == 6


async def test_next_position_isolated_by_status(session: AsyncSession):
    """Positions in other status columns do not affect the answer."""
    session.add(Task(id=uuid.uuid4(), title="p", status="pending", position=7))
    session.add(Task(id=uuid.uuid4(), title="r", status="review", position=42))
    await session.commit()

    assert await _next_position(session, "pending") == 8
    assert await _next_position(session, "review") == 43
    assert await _next_position(session, "scheduled") == 1


async def test_next_position_exclude_id_ignores_specific_task(session: AsyncSession):
    """exclude_id removes that task from the max computation."""
    excluded_id = uuid.uuid4()
    session.add(Task(id=excluded_id, title="e", status="pending", position=10))
    session.add(Task(id=uuid.uuid4(), title="k", status="pending", position=4))
    await session.commit()

    assert await _next_position(session, "pending") == 11
    assert await _next_position(session, "pending", exclude_id=excluded_id) == 5
