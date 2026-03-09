"""Tests for the telemetry module."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import _create_tables
from telemetry import (
    TelemetryBuckets,
    TelemetryReporter,
    collect_active_integrations,
    collect_system_info,
    detect_deployment_type,
    get_or_create_installation_id,
    load_buckets_from_db,
    save_buckets_to_db,
)
import telemetry as telemetry_module


# --- Helpers ---


async def _make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


# --- 6.1 Deployment type detection ---


class TestDeploymentTypeDetection:
    def setup_method(self):
        # Reset cached value
        telemetry_module._deployment_type = None

    def teardown_method(self):
        telemetry_module._deployment_type = None

    @patch("telemetry.Path")
    def test_kubernetes_deployment(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_cls.return_value = mock_path_instance
        assert detect_deployment_type() == "kubernetes"

    @patch.dict(os.environ, {"APPLE_CONTAINER_RUNTIME": "apple"})
    @patch("telemetry.Path")
    def test_macos_desktop_deployment(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_cls.return_value = mock_path_instance
        assert detect_deployment_type() == "macos-desktop"

    @patch.dict(os.environ, {}, clear=True)
    @patch("telemetry.Path")
    def test_docker_other_deployment(self, mock_path_cls):
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_cls.return_value = mock_path_instance
        # Ensure APPLE_CONTAINER_RUNTIME is not set
        os.environ.pop("APPLE_CONTAINER_RUNTIME", None)
        assert detect_deployment_type() == "docker-other"


# --- 6.1 System info ---


def test_collect_system_info():
    info = collect_system_info(worker_count=3)
    assert "os" in info
    assert "arch" in info
    assert "version" in info
    assert info["worker_count"] == 3


# --- 6.2 Hourly bucket accumulator ---


class TestTelemetryBuckets:
    def test_increment_completed(self):
        buckets = TelemetryBuckets()
        buckets.increment_completed()
        buckets.increment_completed()
        result = buckets.get_and_clear()
        assert len(result) == 1
        assert result[0]["tasks_completed"] == 2

    def test_update_max_pending(self):
        buckets = TelemetryBuckets()
        buckets.update_max_pending(5)
        buckets.update_max_pending(3)  # Should not decrease
        buckets.update_max_pending(8)
        result = buckets.get_and_clear()
        assert result[0]["max_pending"] == 8

    def test_set_tasks_scheduled(self):
        buckets = TelemetryBuckets()
        buckets.increment_completed()
        buckets.set_tasks_scheduled(42)
        result = buckets.get_and_clear()
        assert result[0]["tasks_scheduled"] == 42

    def test_get_and_clear_empties_buckets(self):
        buckets = TelemetryBuckets()
        buckets.increment_completed()
        assert not buckets.is_empty()
        buckets.get_and_clear()
        assert buckets.is_empty()

    def test_json_roundtrip(self):
        buckets = TelemetryBuckets()
        buckets.increment_completed()
        buckets.update_max_pending(10)
        json_data = buckets.to_json()

        buckets2 = TelemetryBuckets()
        buckets2.load_from_json(json_data)
        result = buckets2.get_and_clear()
        assert len(result) == 1
        assert result[0]["tasks_completed"] == 1
        assert result[0]["max_pending"] == 10

    def test_disabled_skips_increment(self):
        buckets = TelemetryBuckets()
        buckets.enabled = False
        buckets.increment_completed()
        buckets.update_max_pending(10)
        assert buckets.is_empty()

    def test_re_enabled_resumes_accumulation(self):
        buckets = TelemetryBuckets()
        buckets.enabled = False
        buckets.increment_completed()
        assert buckets.is_empty()
        buckets.enabled = True
        buckets.increment_completed()
        result = buckets.get_and_clear()
        assert len(result) == 1
        assert result[0]["tasks_completed"] == 1

    def test_hour_boundary_rollover(self):
        buckets = TelemetryBuckets()
        # Manually add data for two different hours
        buckets._ensure_bucket("2026-03-09T10:00:00Z")
        buckets._buckets["2026-03-09T10:00:00Z"]["tasks_completed"] = 5
        buckets._ensure_bucket("2026-03-09T11:00:00Z")
        buckets._buckets["2026-03-09T11:00:00Z"]["tasks_completed"] = 3
        result = buckets.get_and_clear()
        assert len(result) == 2
        assert result[0]["hour"] == "2026-03-09T10:00:00Z"
        assert result[0]["tasks_completed"] == 5
        assert result[1]["hour"] == "2026-03-09T11:00:00Z"
        assert result[1]["tasks_completed"] == 3

    @pytest.mark.asyncio
    async def test_persistence_roundtrip(self):
        engine, factory = await _make_session_factory()

        buckets = TelemetryBuckets()
        buckets.increment_completed()
        buckets.increment_completed()
        buckets.update_max_pending(7)

        async with factory() as session:
            await save_buckets_to_db(session, buckets)

        # Load into new buckets instance
        buckets2 = TelemetryBuckets()
        async with factory() as session:
            await load_buckets_from_db(session, buckets2)

        result = buckets2.get_and_clear()
        assert len(result) == 1
        assert result[0]["tasks_completed"] == 2
        assert result[0]["max_pending"] == 7

        await engine.dispose()


# --- 6.3 Telemetry reporter ---


class TestTelemetryReporter:
    @pytest.mark.asyncio
    async def test_successful_post(self):
        engine, factory = await _make_session_factory()
        buckets = TelemetryBuckets()
        buckets.increment_completed()

        reporter = TelemetryReporter(buckets, factory)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("telemetry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with patch.object(telemetry_module, "_deployment_type", "docker-other"):
                await reporter._send_report()

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://cloud.errand.ai/api/telemetry/report"
            payload = call_args[1]["json"]
            assert "installation_id" in payload
            assert payload["deployment_type"] == "docker-other"
            assert len(payload["hourly_buckets"]) == 1

        # Buckets should be cleared after success
        assert buckets.is_empty()

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_failed_post_retains_buckets(self):
        engine, factory = await _make_session_factory()
        buckets = TelemetryBuckets()
        buckets.increment_completed()
        buckets.increment_completed()

        reporter = TelemetryReporter(buckets, factory)

        with patch("telemetry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with patch.object(telemetry_module, "_deployment_type", "docker-other"):
                await reporter._send_report()

        # Buckets should be retained
        assert not buckets.is_empty()
        result = buckets.get_and_clear()
        assert result[0]["tasks_completed"] == 2

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_telemetry_disabled_no_post(self):
        engine, factory = await _make_session_factory()
        buckets = TelemetryBuckets()
        buckets.increment_completed()

        reporter = TelemetryReporter(buckets, factory)

        # Disable via env var
        with patch.dict(os.environ, {"TELEMETRY_ENABLED": "false"}):
            with patch("telemetry.httpx.AsyncClient") as mock_client_cls:
                await reporter._send_report()
                mock_client_cls.assert_not_called()

        # Buckets should remain (not cleared, not sent)
        assert not buckets.is_empty()
        # The enabled flag should have been synced to False
        assert buckets.enabled is False

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_disabled_reporter_stops_accumulation(self):
        """When telemetry is disabled via env var, the reporter syncs the enabled flag
        so subsequent calls to increment_completed/update_max_pending are no-ops."""
        engine, factory = await _make_session_factory()
        buckets = TelemetryBuckets()

        reporter = TelemetryReporter(buckets, factory)

        # Disable via env var and run a report cycle
        with patch.dict(os.environ, {"TELEMETRY_ENABLED": "false"}):
            await reporter._send_report()

        # The flag should be synced
        assert buckets.enabled is False

        # Accumulation calls should be no-ops
        buckets.increment_completed()
        buckets.update_max_pending(100)
        assert buckets.is_empty()

        await engine.dispose()


# --- 6.4 Installation ID ---


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


# --- 6.5 Settings registry ---


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
