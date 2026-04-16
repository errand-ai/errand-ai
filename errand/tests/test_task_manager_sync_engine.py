"""Tests for B5 — the sync engine used by _resolve_provider_sync is cached."""
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
