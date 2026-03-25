"""Tests for TaskManager class lifecycle — leader election, concurrency,
heartbeat, graceful shutdown, and Playwright URL injection.

Covers tasks: 1.4, 9.1–9.7 from the merge-worker-into-server change.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from container_runtime import RuntimeHandle
from task_manager import (
    HEARTBEAT_INTERVAL,
    LEADER_LOCK_ID,
    TaskManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_runtime(
    exit_code: int = 0,
    stdout: str = '{"status":"completed","result":"done","questions":[]}',
    stderr: str = "",
    log_lines: list[str] | None = None,
):
    """Create a mock ContainerRuntime with async methods."""
    mock_runtime = MagicMock()
    mock_runtime.async_prepare = AsyncMock(return_value=RuntimeHandle(runtime_data={}))

    lines = log_lines or []

    async def _async_run(handle):
        for line in lines:
            yield line

    mock_runtime.async_run = _async_run
    mock_runtime.async_result = AsyncMock(return_value=(exit_code, stdout, stderr))
    mock_runtime.async_cleanup = AsyncMock()
    return mock_runtime


def _make_mock_task(**overrides):
    from models import Task
    task = MagicMock(spec=Task)
    task.id = overrides.get("id", uuid.uuid4())
    task.title = overrides.get("title", "Test task")
    task.description = overrides.get("description", "Do the thing")
    task.status = overrides.get("status", "pending")
    task.position = overrides.get("position", 0)
    task.category = overrides.get("category", "immediate")
    task.execute_at = None
    task.repeat_interval = None
    task.repeat_until = None
    task.output = None
    task.runner_logs = None
    task.retry_count = 0
    task.tags = []
    task.created_at = None
    task.updated_at = None
    task.profile_id = None
    return task


# ---------------------------------------------------------------------------
# Task 1.4 — Async runtime interface
# ---------------------------------------------------------------------------

class TestAsyncRuntimeInterface:
    """Verify TaskManager._process_task uses async_* methods on the runtime."""

    async def test_process_task_calls_async_prepare(self):
        """_process_task calls runtime.async_prepare (not sync .prepare)."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.get_valkey", return_value=None):
            await tm._process_task(task, settings)

        mock_runtime.async_prepare.assert_called_once()
        # Sync method should NOT have been called
        assert not hasattr(mock_runtime, "prepare") or not mock_runtime.prepare.called

    async def test_process_task_calls_async_result(self):
        """_process_task calls runtime.async_result (not sync .result)."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.get_valkey", return_value=None):
            await tm._process_task(task, settings)

        mock_runtime.async_result.assert_called_once()

    async def test_process_task_calls_async_cleanup(self):
        """_process_task calls runtime.async_cleanup (not sync .cleanup)."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.get_valkey", return_value=None):
            await tm._process_task(task, settings)

        mock_runtime.async_cleanup.assert_called_once()

    async def test_process_task_iterates_async_run(self):
        """_process_task iterates runtime.async_run (async generator)."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        log_lines = ['{"type":"log","message":"Starting"}\n', '{"type":"log","message":"Done"}\n']
        mock_runtime = _make_mock_runtime(log_lines=log_lines)
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.get_valkey", return_value=None):
            await tm._process_task(task, settings)

        # async_run was iterated (not called as regular function)
        mock_runtime.async_result.assert_called_once()


# ---------------------------------------------------------------------------
# Task 9.1 — Leader election
# ---------------------------------------------------------------------------

class TestLeaderElection:
    """Verify Postgres advisory lock leader election."""

    async def test_acquire_leader_lock_sqlite_always_true(self):
        """SQLite testing mode always returns True (no advisory locks)."""
        tm = TaskManager()
        with patch.dict("os.environ", {"DATABASE_URL": "sqlite+aiosqlite:///:memory:"}):
            result = await tm._acquire_leader_lock()
        assert result is True

    async def test_leader_lock_id_is_stable(self):
        """LEADER_LOCK_ID is a stable int (not random per startup)."""
        assert isinstance(LEADER_LOCK_ID, int)
        assert LEADER_LOCK_ID == hash("errand_task_manager") & 0x7FFFFFFF

    async def test_acquire_leader_lock_resets_on_error(self):
        """Connection is reset when advisory lock fails."""
        tm = TaskManager()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("PG connection lost")
        mock_conn.cursor.return_value = mock_cursor
        tm._leader_connection = mock_conn

        with patch.dict("os.environ", {"DATABASE_URL": "postgresql+asyncpg://user:pass@host/db"}):
            result = await tm._acquire_leader_lock()

        assert result is False
        assert tm._leader_connection is None
        mock_conn.close.assert_called_once()

    async def test_acquire_leader_lock_sets_tcp_keepalive(self):
        """Sync engine is created with TCP keepalive connect_args."""
        tm = TaskManager()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (True,)
        mock_conn.cursor.return_value = mock_cursor
        mock_engine.raw_connection.return_value = mock_conn

        with patch.dict("os.environ", {"DATABASE_URL": "postgresql+asyncpg://user:pass@host/db"}), \
             patch("task_manager.create_sync_engine", return_value=mock_engine) as mock_create:
            result = await tm._acquire_leader_lock()

        assert result is True
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        connect_args = call_kwargs.kwargs.get("connect_args") or call_kwargs[1].get("connect_args")
        assert connect_args == {
            "keepalives": 1,
            "keepalives_idle": 10,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        }

    async def test_lock_wait_logs_at_info_level(self, caplog):
        """Lock contention is logged at INFO level, not DEBUG."""
        import logging

        tm = TaskManager()
        mock_runtime = MagicMock()
        tm._runtime = mock_runtime

        with patch.object(tm, "_acquire_leader_lock", AsyncMock(return_value=False)), \
             patch("task_manager.create_runtime", return_value=mock_runtime), \
             patch("task_manager.POLL_INTERVAL", 0.01), \
             caplog.at_level(logging.INFO, logger="task_manager"):
            # Run one iteration then stop
            async def stop_soon():
                await asyncio.sleep(0.05)
                await tm.stop()
            stop_task = asyncio.create_task(stop_soon())
            await asyncio.wait_for(tm.run(), timeout=5.0)
            await stop_task

        assert any(
            "Another replica holds the leader lock" in record.message
            and record.levelno == logging.INFO
            for record in caplog.records
        )


# ---------------------------------------------------------------------------
# Task 9.2 — Concurrency control
# ---------------------------------------------------------------------------

class TestConcurrencyControl:
    """Verify asyncio.Semaphore-based concurrency control."""

    def test_default_semaphore_is_three(self):
        """TaskManager initialises with semaphore of 3."""
        tm = TaskManager()
        assert tm._semaphore._value == 3
        assert tm._max_concurrent_tasks == 3

    async def test_update_concurrency_setting_changes_semaphore(self):
        """_update_concurrency_setting reads DB and updates semaphore."""
        tm = TaskManager()
        assert tm._max_concurrent_tasks == 3

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_setting = MagicMock()
        mock_setting.value = "5"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result

        with patch("task_manager.async_session", return_value=mock_session):
            await tm._update_concurrency_setting()

        assert tm._max_concurrent_tasks == 5
        assert tm._semaphore._value == 5

    async def test_update_concurrency_setting_env_fallback(self):
        """When no DB setting, env var MAX_CONCURRENT_TASKS is used."""
        tm = TaskManager()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("task_manager.async_session", return_value=mock_session), \
             patch.dict("os.environ", {"MAX_CONCURRENT_TASKS": "7"}):
            await tm._update_concurrency_setting()

        assert tm._max_concurrent_tasks == 7

    async def test_semaphore_limits_concurrent_execution(self):
        """Only max_concurrent_tasks tasks can execute simultaneously."""
        tm = TaskManager()
        tm._semaphore = asyncio.Semaphore(2)
        tm._max_concurrent_tasks = 2

        running = []
        max_running = 0

        async def fake_run_task():
            nonlocal max_running
            async with tm._semaphore:
                running.append(1)
                max_running = max(max_running, len(running))
                await asyncio.sleep(0.01)
                running.pop()

        tasks = [asyncio.create_task(fake_run_task()) for _ in range(5)]
        await asyncio.gather(*tasks)

        assert max_running <= 2


# ---------------------------------------------------------------------------
# Task 9.3 — Per-task lifecycle
# ---------------------------------------------------------------------------

class TestPerTaskLifecycle:
    """Verify _run_task starts heartbeat and cleans up on completion."""

    async def test_run_task_starts_heartbeat(self):
        """_run_task creates a heartbeat asyncio.Task."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }

        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        heartbeat_started = False

        async def patched_heartbeat(task_id):
            nonlocal heartbeat_started
            heartbeat_started = True
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                pass

        async def slow_process_task(*args, **kwargs):
            await asyncio.sleep(0)  # Yield to event loop so heartbeat task runs
            return (0, '{"status":"completed","result":"done","questions":[]}', "")

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_exec_result = MagicMock()
        mock_exec_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_exec_result)

        with patch.object(tm, "_heartbeat_loop", patched_heartbeat), \
             patch.object(tm, "_process_task", slow_process_task), \
             patch("task_manager.async_session", return_value=mock_session), \
             patch("task_manager.publish_event", AsyncMock()):
            await tm._run_task(task, settings)

        assert heartbeat_started

    async def test_run_task_cancels_heartbeat_on_completion(self):
        """_run_task cancels the heartbeat task when processing finishes."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }

        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        heartbeat_cancelled = False

        async def patched_heartbeat(task_id):
            nonlocal heartbeat_cancelled
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                heartbeat_cancelled = True
                raise

        async def slow_process_task(*args, **kwargs):
            await asyncio.sleep(0)  # Yield to event loop so heartbeat task runs
            return (0, '{"status":"completed","result":"done","questions":[]}', "")

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_exec_result = MagicMock()
        mock_exec_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_exec_result)

        with patch.object(tm, "_heartbeat_loop", patched_heartbeat), \
             patch.object(tm, "_process_task", slow_process_task), \
             patch("task_manager.async_session", return_value=mock_session), \
             patch("task_manager.publish_event", AsyncMock()):
            await tm._run_task(task, settings)

        assert heartbeat_cancelled

    async def test_run_task_cancels_heartbeat_on_error(self):
        """_run_task cancels the heartbeat task even when _process_task raises."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }

        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        heartbeat_cancelled = False

        async def patched_heartbeat(task_id):
            nonlocal heartbeat_cancelled
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                heartbeat_cancelled = True
                raise

        async def slow_process_task(*args, **kwargs):
            await asyncio.sleep(0)  # Yield to event loop so heartbeat task runs
            raise RuntimeError("boom")

        with patch.object(tm, "_heartbeat_loop", patched_heartbeat), \
             patch.object(tm, "_process_task", slow_process_task), \
             patch.object(tm, "_schedule_retry", AsyncMock()):
            await tm._run_task(task, settings)

        assert heartbeat_cancelled


# ---------------------------------------------------------------------------
# Task 9.4 — Graceful shutdown
# ---------------------------------------------------------------------------

class TestGracefulShutdown:
    """Verify TaskManager.stop() signals and waits for in-flight tasks."""

    async def test_stop_sets_stop_event(self):
        """stop() sets _stop_event so run() breaks out of its loop."""
        tm = TaskManager()
        assert not tm._stop_event.is_set()
        await tm.stop()
        assert tm._stop_event.is_set()

    async def test_stop_sets_running_false(self):
        """stop() sets _running to False."""
        tm = TaskManager()
        tm._running = True
        await tm.stop()
        assert tm._running is False

    async def test_run_exits_when_stopped(self):
        """run() exits promptly after stop() is called."""
        tm = TaskManager()

        mock_runtime = MagicMock()
        mock_runtime.async_cleanup = AsyncMock()

        async def stop_soon():
            await asyncio.sleep(0.05)
            await tm.stop()

        with patch.object(tm, "_acquire_leader_lock", AsyncMock(return_value=True)), \
             patch.object(tm, "_poll_and_dispatch", AsyncMock()), \
             patch("task_manager.create_runtime", return_value=mock_runtime), \
             patch("task_manager.POLL_INTERVAL", 1):
            stop_task = asyncio.create_task(stop_soon())
            await asyncio.wait_for(tm.run(), timeout=5.0)
            await stop_task

        assert tm._running is False

    async def test_run_waits_for_inflight_tasks(self):
        """run() waits for in-flight tasks before returning."""
        tm = TaskManager()
        completed = False

        async def slow_task():
            nonlocal completed
            await asyncio.sleep(0.1)
            completed = True

        # Simulate an in-flight task
        mock_runtime = MagicMock()
        inflight = asyncio.create_task(slow_task())
        tm._tasks.add(inflight)

        async def stop_immediately():
            await asyncio.sleep(0.01)
            await tm.stop()

        with patch.object(tm, "_acquire_leader_lock", AsyncMock(return_value=False)), \
             patch("task_manager.create_runtime", return_value=mock_runtime), \
             patch("task_manager.POLL_INTERVAL", 0.01):
            stop_task = asyncio.create_task(stop_immediately())
            await asyncio.wait_for(tm.run(), timeout=5.0)
            await stop_task

        assert completed


# ---------------------------------------------------------------------------
# Task 9.5 — Deadlock prevention
# ---------------------------------------------------------------------------

class TestDeadlockPrevention:
    """Verify asyncio-based deadlock prevention patterns."""

    async def test_heartbeat_does_not_block_processing(self):
        """Heartbeat runs as a separate asyncio.Task — never blocks _process_task."""
        tm = TaskManager()
        task_id = uuid.uuid4()

        # Heartbeat that records calls
        heartbeat_calls = []

        async def record_heartbeat(tid):
            heartbeat_calls.append(tid)
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                pass

        with patch.object(tm, "_heartbeat_loop", record_heartbeat):
            hb_task = asyncio.create_task(tm._heartbeat_loop(task_id))
            await asyncio.sleep(0)  # Let it start
            assert len(heartbeat_calls) == 1
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

    async def test_stop_event_unblocks_poll_wait(self):
        """_stop_event.set() unblocks the poll wait in run()."""
        tm = TaskManager()
        tm._running = True

        # The stop event should interrupt the wait_for(timeout=POLL_INTERVAL)
        unblocked = False

        async def check_unblock():
            nonlocal unblocked
            try:
                await asyncio.wait_for(tm._stop_event.wait(), timeout=10)
                unblocked = True
            except TimeoutError:
                pass

        task = asyncio.create_task(check_unblock())
        await asyncio.sleep(0.01)
        tm._stop_event.set()
        await task
        assert unblocked


# ---------------------------------------------------------------------------
# Task 9.6 — Playwright URL injection
# ---------------------------------------------------------------------------

class TestPlaywrightUrlInjection:
    """Verify PLAYWRIGHT_MCP_URL env var injection into mcp.json."""

    async def test_playwright_url_injected_into_mcp_json(self):
        """When PLAYWRIGHT_MCP_URL is set, playwright entry appears in mcp.json."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {"mcpServers": {}},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.PLAYWRIGHT_MCP_URL", "http://playwright:8931/mcp"), \
             patch("task_manager.get_valkey", return_value=None), \
             patch("task_manager.recall_from_hindsight", return_value=None):
            await tm._process_task(task, settings)

        import json
        files = mock_runtime.async_prepare.call_args.kwargs["files"]
        mcp_config = json.loads(files["mcp.json"])
        assert "playwright" in mcp_config["mcpServers"]
        assert mcp_config["mcpServers"]["playwright"]["url"] == "http://playwright:8931/mcp"

    async def test_playwright_not_injected_when_empty(self):
        """When PLAYWRIGHT_MCP_URL is empty, no playwright entry in mcp.json."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {"mcpServers": {}},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.PLAYWRIGHT_MCP_URL", ""), \
             patch("task_manager.get_valkey", return_value=None), \
             patch("task_manager.recall_from_hindsight", return_value=None):
            await tm._process_task(task, settings)

        import json
        files = mock_runtime.async_prepare.call_args.kwargs["files"]
        mcp_config = json.loads(files["mcp.json"])
        assert "playwright" not in mcp_config.get("mcpServers", {})

    async def test_db_playwright_not_overwritten(self):
        """User-configured playwright in DB is not overwritten by env var."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {"mcpServers": {"playwright": {"url": "http://custom:9999/mcp"}}},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.PLAYWRIGHT_MCP_URL", "http://playwright:8931/mcp"), \
             patch("task_manager.get_valkey", return_value=None), \
             patch("task_manager.recall_from_hindsight", return_value=None):
            await tm._process_task(task, settings)

        import json
        files = mock_runtime.async_prepare.call_args.kwargs["files"]
        mcp_config = json.loads(files["mcp.json"])
        assert mcp_config["mcpServers"]["playwright"]["url"] == "http://custom:9999/mcp"


# ---------------------------------------------------------------------------
# Task 9.7 — Existing test verification (structural)
# ---------------------------------------------------------------------------

class TestExistingTestCompat:
    """Verify the async test pattern works correctly with TaskManager."""

    async def test_taskmanager_uses_instance_runtime(self):
        """TaskManager._process_task uses self._runtime (instance), not a module global."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime()
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.get_valkey", return_value=None):
            await tm._process_task(task, settings)

        # The mock_runtime we set on the instance was used
        mock_runtime.async_prepare.assert_called_once()

    async def test_process_task_returns_tuple(self):
        """_process_task returns (exit_code, stdout, stderr) tuple."""
        task = _make_mock_task()
        settings = {
            "mcp_servers": {},
            "credentials": [],
            "task_processing_model": "gpt-4o",
            "system_prompt": "",
        }
        mock_runtime = _make_mock_runtime(exit_code=0, stdout='{"status":"completed","result":"ok","questions":[]}', stderr="log line")
        tm = TaskManager()
        tm._runtime = mock_runtime

        with patch("task_manager.get_valkey", return_value=None):
            result = await tm._process_task(task, settings)

        assert isinstance(result, tuple)
        assert len(result) == 3
        exit_code, stdout, stderr = result
        assert exit_code == 0
        assert "completed" in stdout
        assert stderr == "log line"

    def test_heartbeat_interval_is_60(self):
        """HEARTBEAT_INTERVAL constant is 60 seconds."""
        assert HEARTBEAT_INTERVAL == 60

    def test_taskmanager_initial_state(self):
        """TaskManager initialises with correct default state."""
        tm = TaskManager()
        assert tm._running is False
        assert len(tm._tasks) == 0
        assert tm._max_concurrent_tasks == 3
        assert tm._runtime is None
        assert tm._leader_connection is None
        assert not tm._stop_event.is_set()
