"""Tests for worker heartbeat functionality."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from worker import (
    _update_heartbeat,
    HEARTBEAT_INTERVAL,
    process_task_in_container,
)
from container_runtime import RuntimeHandle


def _make_mock_task():
    task = MagicMock()
    task.id = uuid.uuid4()
    task.title = "Test task"
    task.description = "Test"
    task.status = "running"
    task.category = "immediate"
    task.retry_count = 0
    task.questions = None
    return task


def _base_settings():
    return {
        "task_processing_model": "gpt-4",
        "system_prompt": "You are helpful.",
    }


def _make_mock_runtime(log_lines=None):
    mock = MagicMock()
    mock.prepare.return_value = RuntimeHandle(runtime_data={})
    mock.run.return_value = iter(log_lines or [])
    mock.result.return_value = (0, '{"status":"completed","result":"done","questions":[]}', "")
    return mock


# --- heartbeat_at set on running (tested via run_worker, but we test the helper here) ---


def test_update_heartbeat_calls_db():
    """_update_heartbeat executes an UPDATE against the sync engine."""
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    with patch("worker._get_sync_engine", return_value=mock_engine):
        _update_heartbeat(uuid.uuid4())

    mock_conn.execute.assert_called_once()
    mock_conn.commit.assert_called_once()


def test_update_heartbeat_failure_does_not_raise():
    """_update_heartbeat logs a warning but doesn't raise on DB error."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("DB connection failed")

    with patch("worker._get_sync_engine", return_value=mock_engine):
        # Should not raise
        _update_heartbeat(uuid.uuid4())


# --- Heartbeat called during log streaming ---


def test_heartbeat_called_during_long_streaming():
    """Heartbeat is updated when log streaming exceeds the interval."""
    task = _make_mock_task()
    settings = _base_settings()

    # Simulate log lines with time advancing past heartbeat interval
    call_count = 0
    original_monotonic = time.monotonic

    def fake_monotonic():
        nonlocal call_count
        call_count += 1
        # First call (last_token_refresh init): 0
        # Second call (last_heartbeat init): 0
        # After that, each call advances by 35s so 2nd line triggers heartbeat
        return original_monotonic() + (call_count - 2) * 35 if call_count > 2 else original_monotonic()

    mock_runtime = _make_mock_runtime(log_lines=["line1", "line2", "line3"])

    import worker
    original_runtime = worker.container_runtime
    worker.container_runtime = mock_runtime

    try:
        with patch("worker._update_heartbeat") as mock_hb, \
             patch("time.monotonic", side_effect=fake_monotonic), \
             patch.dict("os.environ", {"OPENAI_BASE_URL": "http://litellm:4000", "OPENAI_API_KEY": "sk-test"}):
            process_task_in_container(task, settings)
    finally:
        worker.container_runtime = original_runtime

    # Heartbeat should have been called at least once
    assert mock_hb.call_count >= 1
    mock_hb.assert_called_with(task.id)


def test_heartbeat_not_called_for_short_streaming():
    """Heartbeat is not called when streaming completes quickly."""
    task = _make_mock_task()
    settings = _base_settings()

    mock_runtime = _make_mock_runtime(log_lines=["line1"])

    import worker
    original_runtime = worker.container_runtime
    worker.container_runtime = mock_runtime

    try:
        with patch("worker._update_heartbeat") as mock_hb, \
             patch.dict("os.environ", {"OPENAI_BASE_URL": "http://litellm:4000", "OPENAI_API_KEY": "sk-test"}):
            process_task_in_container(task, settings)
    finally:
        worker.container_runtime = original_runtime

    # Heartbeat should not be called (streaming finishes in << 60s)
    mock_hb.assert_not_called()
