"""Tests for B5 — the sync engine used by _resolve_provider_sync is cached."""
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import task_manager


def test_get_sync_engine_creates_once(monkeypatch):
    """Repeated calls reuse the same engine and only invoke create_engine once."""
    # Reset the module-level cache so the test is deterministic.
    monkeypatch.setattr(task_manager, "_sync_engine", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    sentinel_engine = MagicMock(name="sync_engine")
    with patch.object(task_manager, "create_sync_engine", return_value=sentinel_engine) as mock_create:
        first = task_manager._get_sync_engine()
        second = task_manager._get_sync_engine()
        third = task_manager._get_sync_engine()

    assert first is sentinel_engine
    assert second is first
    assert third is first
    assert mock_create.call_count == 1


def test_get_sync_engine_is_thread_safe(monkeypatch):
    """Concurrent callers from multiple threads must share a single engine.

    _resolve_provider_sync runs inside loop.run_in_executor, so bursts of
    concurrent lookups arrive on different threads. A naive ``is None``
    check would race and leak pools — the lock must serialise init.

    To expose such a race we delay engine construction inside the lock; all
    threads start at a barrier so they pile up at _get_sync_engine together.
    """
    monkeypatch.setattr(task_manager, "_sync_engine", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    sentinel_engine = MagicMock(name="sync_engine")

    def _slow_create_engine(*_args, **_kwargs):
        # Widen the race window — if the lock is missing, other threads
        # will see ``_sync_engine is None`` during this sleep and each build
        # their own engine.
        import time
        time.sleep(0.05)
        return sentinel_engine

    n_threads = 8
    ready = threading.Barrier(n_threads)

    def _worker(_):
        ready.wait(timeout=2)
        return task_manager._get_sync_engine()

    with patch.object(task_manager, "create_sync_engine", side_effect=_slow_create_engine) as mock_create:
        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            results = list(pool.map(_worker, range(n_threads)))

    assert all(r is sentinel_engine for r in results)
    assert mock_create.call_count == 1


def test_resolve_provider_sync_reuses_cached_engine(monkeypatch):
    """Multiple _resolve_provider_sync calls share the single cached engine."""
    monkeypatch.setattr(task_manager, "_sync_engine", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    # Fake engine whose .connect() returns a context manager yielding a conn
    # whose execute().fetchone() returns a provider row.
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = ("https://llm.example", b"encrypted")
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False

    with patch.object(task_manager, "create_sync_engine", return_value=engine) as mock_create:
        with patch("llm_providers.decrypt_api_key", return_value="plaintext"):
            first = task_manager._resolve_provider_sync("provider-a")
            second = task_manager._resolve_provider_sync("provider-b")

    assert first == {"base_url": "https://llm.example", "api_key": "plaintext"}
    assert second == first
    assert mock_create.call_count == 1
