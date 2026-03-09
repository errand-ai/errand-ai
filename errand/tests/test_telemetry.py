"""Tests for the telemetry module."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import _create_tables
from telemetry import (
    TelemetryReporter,
    collect_active_integrations,
    collect_hourly_metrics,
    collect_system_info,
    detect_deployment_type,
    get_or_create_installation_id,
)


# --- Helpers ---


async def _make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def _insert_completed_task(factory, updated_at: datetime):
    """Insert a task with 'completed' status and a specific updated_at."""
    async with factory() as session:
        task_id = str(uuid.uuid4())
        await session.execute(
            text(
                "INSERT INTO tasks (id, title, status, created_at, updated_at, position) "
                "VALUES (:id, 'test', 'completed', :now, :updated, 0)"
            ),
            {"id": task_id, "now": datetime.now(timezone.utc), "updated": updated_at},
        )
        await session.commit()
    return task_id


# --- Deployment type detection ---


class TestDeploymentTypeDetection:
    @patch("telemetry._deployment_type", new=None)
    @patch("telemetry.Path")
    def test_kubernetes_deployment(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_cls.return_value = mock_path_instance
        assert detect_deployment_type() == "kubernetes"

    @patch("telemetry._deployment_type", new=None)
    @patch.dict(os.environ, {"ERRAND_CONTAINER_RUNTIME": "apple-container"})
    @patch("telemetry.Path")
    def test_apple_container_deployment(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_cls.return_value = mock_path_instance
        assert detect_deployment_type() == "apple-container"

    @patch("telemetry._deployment_type", new=None)
    @patch.dict(os.environ, {"ERRAND_CONTAINER_RUNTIME": "apple-docker"})
    @patch("telemetry.Path")
    def test_apple_docker_deployment(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_cls.return_value = mock_path_instance
        assert detect_deployment_type() == "apple-docker"

    @patch("telemetry._deployment_type", new=None)
    @patch.dict(os.environ, {"ERRAND_CONTAINER_RUNTIME": "linux-docker"})
    @patch("telemetry.Path")
    def test_custom_runtime_passthrough(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_cls.return_value = mock_path_instance
        assert detect_deployment_type() == "linux-docker"

    @patch("telemetry._deployment_type", new=None)
    @patch.dict(os.environ, {}, clear=True)
    @patch("telemetry.Path")
    def test_default_unknown_docker(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_cls.return_value = mock_path_instance
        os.environ.pop("ERRAND_CONTAINER_RUNTIME", None)
        assert detect_deployment_type() == "unknown-docker"


# --- System info ---


def test_collect_system_info():
    info = collect_system_info(worker_count=3)
    assert "os" in info
    assert "arch" in info
    assert "version" in info
    assert info["worker_count"] == 3


# --- Hourly metrics from database ---


class TestHourlyMetrics:
    @pytest.mark.asyncio
    async def test_completed_tasks_grouped_by_hour(self):
        engine, factory = await _make_session_factory()

        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        await _insert_completed_task(factory, now)
        await _insert_completed_task(factory, now)
        await _insert_completed_task(factory, hour_ago)

        async with factory() as session:
            metrics = await collect_hourly_metrics(session, now - timedelta(hours=2))

        assert len(metrics) == 2
        total_completed = sum(m["tasks_completed"] for m in metrics)
        assert total_completed == 3

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_no_tasks_returns_current_hour_zero(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            metrics = await collect_hourly_metrics(session, None)

        assert len(metrics) == 1
        assert metrics[0]["tasks_completed"] == 0

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_since_filter_excludes_older_tasks(self):
        engine, factory = await _make_session_factory()

        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=10)
        recent = now - timedelta(minutes=30)
        await _insert_completed_task(factory, old)
        await _insert_completed_task(factory, recent)

        since = now - timedelta(hours=1)
        async with factory() as session:
            metrics = await collect_hourly_metrics(session, since)

        total = sum(m["tasks_completed"] for m in metrics)
        assert total == 1

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_includes_pending_and_scheduled_counts(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, updated_at, position) "
                    "VALUES (:id, 'p1', 'pending', :now, :now, 0)"
                ),
                {"id": str(uuid.uuid4()), "now": datetime.now(timezone.utc)},
            )
            await session.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, updated_at, position) "
                    "VALUES (:id, 's1', 'scheduled', :now, :now, 0)"
                ),
                {"id": str(uuid.uuid4()), "now": datetime.now(timezone.utc)},
            )
            await session.commit()

        async with factory() as session:
            metrics = await collect_hourly_metrics(session, None)

        assert metrics[0]["max_pending"] == 1
        assert metrics[0]["tasks_scheduled"] == 1

        await engine.dispose()


# --- Telemetry reporter ---


class TestTelemetryReporter:
    @pytest.mark.asyncio
    async def test_successful_post(self):
        engine, factory = await _make_session_factory()

        reporter = TelemetryReporter(factory)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)
        mock_valkey.delete = AsyncMock()

        with patch("telemetry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with patch("telemetry._deployment_type", "unknown-docker"), \
                 patch("telemetry.get_valkey", return_value=mock_valkey):
                await reporter._send_report()

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://service.errand.cloud/api/telemetry/report"
            payload = call_args[1]["json"]
            assert "installation_id" in payload
            assert payload["deployment_type"] == "unknown-docker"
            assert "hourly_buckets" in payload

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_failed_post_does_not_update_last_report(self):
        engine, factory = await _make_session_factory()

        reporter = TelemetryReporter(factory)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)
        mock_valkey.delete = AsyncMock()

        with patch("telemetry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with patch("telemetry._deployment_type", "unknown-docker"), \
                 patch("telemetry.get_valkey", return_value=mock_valkey):
                await reporter._send_report()

        # last_report_at should not be set
        async with factory() as session:
            from sqlalchemy import select
            from models import Setting
            result = await session.execute(
                select(Setting).where(Setting.key == "telemetry_last_report_at")
            )
            assert result.scalar_one_or_none() is None

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_telemetry_disabled_no_post(self):
        engine, factory = await _make_session_factory()

        reporter = TelemetryReporter(factory)

        with patch.dict(os.environ, {"TELEMETRY_ENABLED": "false"}):
            with patch("telemetry.httpx.AsyncClient") as mock_client_cls:
                with patch("telemetry.get_valkey") as mock_get_valkey:
                    await reporter._send_report()
                    mock_client_cls.assert_not_called()
                    # Should not even try to acquire lock
                    mock_get_valkey.assert_not_called()

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_skips_report(self):
        engine, factory = await _make_session_factory()

        reporter = TelemetryReporter(factory)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=False)
        mock_valkey.get = AsyncMock(return_value="other-host")

        with patch("telemetry.get_valkey", return_value=mock_valkey):
            with patch("telemetry.httpx.AsyncClient") as mock_client_cls:
                await reporter._send_report()
                mock_client_cls.assert_not_called()

        await engine.dispose()


# --- Installation ID ---


class TestInstallationId:
    @pytest.mark.asyncio
    async def test_generates_uuid_on_first_run(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            install_id = await get_or_create_installation_id(session)

        assert len(install_id) == 36  # UUID format
        assert install_id.count("-") == 4

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_reuses_existing_uuid(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            id1 = await get_or_create_installation_id(session)

        async with factory() as session:
            id2 = await get_or_create_installation_id(session)

        assert id1 == id2

        await engine.dispose()


# --- Settings registry ---


def test_telemetry_enabled_in_registry():
    from settings_registry import SETTINGS_REGISTRY

    assert "telemetry_enabled" in SETTINGS_REGISTRY
    entry = SETTINGS_REGISTRY["telemetry_enabled"]
    assert entry["env_var"] == "TELEMETRY_ENABLED"
    assert entry["sensitive"] is False
    assert entry["default"] is True


@pytest.mark.asyncio
async def test_telemetry_enabled_resolves_default():
    from settings_registry import resolve_settings

    engine, factory = await _make_session_factory()

    async with factory() as session:
        result = await resolve_settings(session)

    assert "telemetry_enabled" in result
    assert result["telemetry_enabled"]["value"] is True
    assert result["telemetry_enabled"]["source"] == "default"

    await engine.dispose()


@pytest.mark.asyncio
async def test_telemetry_enabled_env_override():
    from settings_registry import resolve_settings

    engine, factory = await _make_session_factory()

    with patch.dict(os.environ, {"TELEMETRY_ENABLED": "false"}):
        async with factory() as session:
            result = await resolve_settings(session)

    assert result["telemetry_enabled"]["value"] == "false"
    assert result["telemetry_enabled"]["source"] == "env"
    assert result["telemetry_enabled"]["readonly"] is True

    await engine.dispose()


# --- Active integrations ---


class TestActiveIntegrations:
    @pytest.mark.asyncio
    async def test_collects_connected_integrations(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO platform_credentials (platform_id, encrypted_data, status) "
                    "VALUES ('github', 'enc_data', 'connected')"
                )
            )
            await session.execute(
                text(
                    "INSERT INTO platform_credentials (platform_id, encrypted_data, status) "
                    "VALUES ('slack', 'enc_data', 'disconnected')"
                )
            )
            await session.commit()

        async with factory() as session:
            integrations = await collect_active_integrations(session)

        assert integrations == ["github"]

        await engine.dispose()
