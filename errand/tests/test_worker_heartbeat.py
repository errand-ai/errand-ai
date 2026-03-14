"""Tests for TaskManager heartbeat functionality."""
import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from task_manager import TaskManager, HEARTBEAT_INTERVAL


@pytest.mark.asyncio
async def test_heartbeat_loop_updates_db():
    """_heartbeat_loop updates heartbeat_at in the database."""
    tm = TaskManager()
    task_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    with patch("task_manager.async_session", return_value=mock_session), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        try:
            await tm._heartbeat_loop(task_id)
        except asyncio.CancelledError:
            pass

    # Should have called execute + commit at least once
    assert mock_session.execute.call_count >= 1
    assert mock_session.commit.call_count >= 1


@pytest.mark.asyncio
async def test_heartbeat_loop_db_failure_does_not_crash():
    """_heartbeat_loop logs a warning but continues on DB error."""
    tm = TaskManager()
    task_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute.side_effect = Exception("DB connection failed")

    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    with patch("task_manager.async_session", return_value=mock_session), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        try:
            await tm._heartbeat_loop(task_id)
        except asyncio.CancelledError:
            pass

    # Should not have raised — the DB error is caught internally
    assert mock_session.execute.call_count >= 1


@pytest.mark.asyncio
async def test_heartbeat_loop_cancelled_cleanly():
    """_heartbeat_loop exits cleanly when cancelled."""
    tm = TaskManager()
    task_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # Cancel immediately on first sleep
    async def cancel_sleep(seconds):
        raise asyncio.CancelledError()

    with patch("task_manager.async_session", return_value=mock_session), \
         patch("asyncio.sleep", side_effect=cancel_sleep):
        # Should not raise
        await tm._heartbeat_loop(task_id)


@pytest.mark.asyncio
async def test_heartbeat_interval_constant():
    """HEARTBEAT_INTERVAL is 60 seconds."""
    assert HEARTBEAT_INTERVAL == 60
