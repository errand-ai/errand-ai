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
    _read_cgroup_cpu_limit,
    _read_cgroup_memory_limit,
    classify_provider_url,
    collect_active_integrations,
    collect_health_snapshot,
    collect_hourly_metrics,
    collect_llm_config,
    collect_postgres_version,
    collect_system_info,
    collect_system_metrics,
    collect_valkey_info,
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


# --- Cgroup memory limit detection ---


class TestCgroupMemoryLimit:
    @patch("telemetry.Path")
    def test_cgroup_v2_numeric_limit(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.return_value = "536870912\n"  # 512 MB
        mock_path_cls.return_value = mock_path
        result = _read_cgroup_memory_limit()
        assert result == 512

    @patch("telemetry.Path")
    def test_cgroup_v2_max_returns_none(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.return_value = "max\n"
        mock_path_cls.return_value = mock_path
        result = _read_cgroup_memory_limit()
        assert result is None

    @patch("telemetry.psutil")
    @patch("telemetry.Path")
    def test_cgroup_v1_limit_below_host(self, mock_path_cls, mock_psutil):
        mock_psutil.virtual_memory.return_value = MagicMock(total=8 * 1024**3)

        def path_side_effect(p):
            mock = MagicMock()
            if p == "/sys/fs/cgroup/memory.max":
                mock.read_text.side_effect = FileNotFoundError
            elif p == "/sys/fs/cgroup/memory/memory.limit_in_bytes":
                mock.read_text.return_value = str(1024 * 1024 * 1024)  # 1 GB
            return mock

        mock_path_cls.side_effect = path_side_effect
        result = _read_cgroup_memory_limit()
        assert result == 1024

    @patch("telemetry.Path")
    def test_no_cgroup_files_returns_none(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.side_effect = FileNotFoundError
        mock_path_cls.return_value = mock_path
        result = _read_cgroup_memory_limit()
        assert result is None


# --- Cgroup CPU limit detection ---


class TestCgroupCpuLimit:
    @patch("telemetry.Path")
    def test_cgroup_v2_cpu_limit(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.return_value = "200000 100000\n"  # 2.0 CPUs
        mock_path_cls.return_value = mock_path
        result = _read_cgroup_cpu_limit()
        assert result == 2.0

    @patch("telemetry.Path")
    def test_cgroup_v2_max_cpu_returns_none(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.return_value = "max 100000\n"
        mock_path_cls.return_value = mock_path
        result = _read_cgroup_cpu_limit()
        assert result is None

    @patch("telemetry.Path")
    def test_cgroup_v1_cpu_limit(self, mock_path_cls):
        def path_side_effect(p):
            mock = MagicMock()
            if p == "/sys/fs/cgroup/cpu.max":
                mock.read_text.side_effect = FileNotFoundError
            elif p == "/sys/fs/cgroup/cpu/cpu.cfs_quota_us":
                mock.read_text.return_value = "150000\n"
            elif p == "/sys/fs/cgroup/cpu/cpu.cfs_period_us":
                mock.read_text.return_value = "100000\n"
            return mock

        mock_path_cls.side_effect = path_side_effect
        result = _read_cgroup_cpu_limit()
        assert result == 1.5

    @patch("telemetry.Path")
    def test_cgroup_v1_unlimited_cpu(self, mock_path_cls):
        def path_side_effect(p):
            mock = MagicMock()
            if p == "/sys/fs/cgroup/cpu.max":
                mock.read_text.side_effect = FileNotFoundError
            elif p == "/sys/fs/cgroup/cpu/cpu.cfs_quota_us":
                mock.read_text.return_value = "-1\n"
            return mock

        mock_path_cls.side_effect = path_side_effect
        result = _read_cgroup_cpu_limit()
        assert result is None

    @patch("telemetry.Path")
    def test_no_cgroup_cpu_files_returns_none(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.side_effect = FileNotFoundError
        mock_path_cls.return_value = mock_path
        result = _read_cgroup_cpu_limit()
        assert result is None


# --- classify_provider_url ---


class TestClassifyProviderUrl:
    def test_openai(self):
        assert classify_provider_url("https://api.openai.com/v1", "openai_compatible") == "openai"

    def test_anthropic(self):
        assert classify_provider_url("https://api.anthropic.com/v1", "litellm") == "anthropic"

    def test_gemini(self):
        assert classify_provider_url("https://generativelanguage.googleapis.com/v1", "litellm") == "gemini"

    def test_xai(self):
        assert classify_provider_url("https://api.x.ai/v1", "openai_compatible") == "xai"

    def test_ollama_localhost(self):
        assert classify_provider_url("http://localhost:11434", "openai_compatible") == "ollama"

    def test_ollama_127(self):
        assert classify_provider_url("http://127.0.0.1:11434/v1", "openai_compatible") == "ollama"

    def test_litellm_other(self):
        assert classify_provider_url("https://my-litellm.company.com/v1", "litellm") == "litellm-other"

    def test_openai_compatible_other(self):
        assert classify_provider_url("https://my-proxy.company.com/v1", "openai_compatible") == "openai-compatible-other"

    def test_completely_unknown(self):
        assert classify_provider_url("https://custom-ai.example.com", "unknown") == "other"

    def test_case_insensitive(self):
        assert classify_provider_url("https://API.OPENAI.COM/v1", "openai_compatible") == "openai"

    def test_well_known_host_in_path_not_misclassified(self):
        # Host is evil.example.com; "api.openai.com" appears only in the path.
        assert (
            classify_provider_url(
                "https://evil.example.com/api.openai.com/v1", "openai_compatible"
            )
            == "openai-compatible-other"
        )

    def test_well_known_host_as_subdomain_suffix_not_misclassified(self):
        # Hostname is api.openai.com.attacker.example, which is NOT api.openai.com.
        assert (
            classify_provider_url(
                "https://api.openai.com.attacker.example/v1", "openai_compatible"
            )
            == "openai-compatible-other"
        )

    def test_malformed_empty_string_falls_through(self):
        # Empty string has no hostname; should fall through without raising.
        assert classify_provider_url("", "openai_compatible") == "openai-compatible-other"
        assert classify_provider_url("", "litellm") == "litellm-other"
        assert classify_provider_url("", "unknown") == "other"

    def test_malformed_missing_scheme_falls_through(self):
        # Without a scheme, urlparse cannot extract a hostname; should fall through.
        assert (
            classify_provider_url("api.openai.com/v1", "openai_compatible")
            == "openai-compatible-other"
        )

    def test_ollama_wrong_port_not_classified(self):
        # localhost on a non-Ollama port should not be classified as ollama.
        assert (
            classify_provider_url("http://localhost:8080", "openai_compatible")
            == "openai-compatible-other"
        )


# --- collect_system_metrics ---


class TestCollectSystemMetrics:
    @patch("telemetry._cached_static_metrics", new=None)
    @patch("telemetry._read_cgroup_cpu_limit", return_value=None)
    @patch("telemetry._read_cgroup_memory_limit", return_value=None)
    @patch("telemetry.psutil")
    def test_collects_all_fields(self, mock_psutil, _mock_mem, _mock_cpu):
        mock_psutil.cpu_count.return_value = 4
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=8 * 1024**3,
            available=4 * 1024**3,
        )
        mock_psutil.disk_usage.return_value = MagicMock(free=50 * 1024**3)

        metrics = collect_system_metrics()

        assert metrics["cpu_count"] == 4
        assert metrics["memory_total_mb"] == 8192
        assert metrics["memory_available_mb"] == 4096
        assert metrics["disk_available_mb"] == 51200
        assert metrics["container_memory_limit_mb"] is None
        assert metrics["container_cpu_limit"] is None

    @patch("telemetry._cached_static_metrics", {"cpu_count": 2, "memory_total_mb": 4096, "container_memory_limit_mb": None, "container_cpu_limit": None})
    @patch("telemetry.psutil")
    def test_reuses_cached_static_values(self, mock_psutil):
        mock_psutil.virtual_memory.return_value = MagicMock(available=2 * 1024**3)
        mock_psutil.disk_usage.return_value = MagicMock(free=10 * 1024**3)

        metrics = collect_system_metrics()

        # Static values from cache
        assert metrics["cpu_count"] == 2
        assert metrics["memory_total_mb"] == 4096
        # Dynamic values re-read
        assert metrics["memory_available_mb"] == 2048
        assert metrics["disk_available_mb"] == 10240
        # psutil.cpu_count should NOT have been called (cached)
        mock_psutil.cpu_count.assert_not_called()


# --- collect_postgres_version ---


class TestCollectPostgresVersion:
    @pytest.mark.asyncio
    async def test_parses_postgresql_version_string(self):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "PostgreSQL 16.2 on x86_64-pc-linux-gnu"
        mock_session.execute = AsyncMock(return_value=mock_result)

        version = await collect_postgres_version(mock_session)
        assert version == "16.2"

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(side_effect=Exception("connection error"))
        version = await collect_postgres_version(mock_session)
        assert version is None


# --- collect_valkey_info ---


class TestCollectValkeyInfo:
    @pytest.mark.asyncio
    async def test_valkey_connected_with_version(self):
        mock_valkey = AsyncMock()
        mock_valkey.info = AsyncMock(return_value={"redis_version": "7.2.4"})

        with patch("telemetry.get_valkey", return_value=mock_valkey):
            version, connected = await collect_valkey_info()

        assert version == "7.2.4"
        assert connected is True

    @pytest.mark.asyncio
    async def test_valkey_connected_info_restricted(self):
        mock_valkey = AsyncMock()
        mock_valkey.info = AsyncMock(side_effect=Exception("NOPERM"))

        with patch("telemetry.get_valkey", return_value=mock_valkey):
            version, connected = await collect_valkey_info()

        assert version is None
        assert connected is True

    @pytest.mark.asyncio
    async def test_valkey_not_configured(self):
        with patch("telemetry.get_valkey", return_value=None):
            version, connected = await collect_valkey_info()

        assert version is None
        assert connected is False


# --- collect_llm_config ---


class TestCollectLlmConfig:
    @pytest.mark.asyncio
    async def test_collects_providers_and_models(self):
        engine, factory = await _make_session_factory()

        provider_id = str(uuid.uuid4())
        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO llm_providers (id, name, base_url, api_key_encrypted, provider_type) "
                    "VALUES (:id, 'openai', 'https://api.openai.com/v1', 'enc', 'openai_compatible')"
                ),
                {"id": provider_id},
            )
            await session.execute(
                text(
                    "INSERT INTO settings (key, value, updated_at) "
                    "VALUES ('llm_model', :val, :now)"
                ),
                {
                    "val": '{"provider_id": "' + provider_id + '", "model": "gpt-4o"}',
                    "now": datetime.now(timezone.utc),
                },
            )
            await session.commit()

        async with factory() as session:
            config = await collect_llm_config(session)

        assert len(config["providers"]) == 1
        assert config["providers"][0]["type"] == "openai_compatible"
        assert config["providers"][0]["category"] == "openai"
        assert "llm_model" in config["models"]
        assert config["models"]["llm_model"]["model"] == "gpt-4o"
        assert config["models"]["llm_model"]["category"] == "openai"

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_empty_state(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            config = await collect_llm_config(session)

        assert config["providers"] == []
        assert config["models"] == {}

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_model_without_provider_gets_other_category(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO settings (key, value, updated_at) "
                    "VALUES ('task_processing_model', :val, :now)"
                ),
                {
                    "val": '{"provider_id": null, "model": "gpt-4o-mini"}',
                    "now": datetime.now(timezone.utc),
                },
            )
            await session.commit()

        async with factory() as session:
            config = await collect_llm_config(session)

        assert "task_processing_model" in config["models"]
        assert config["models"]["task_processing_model"]["category"] == "other"

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_legacy_string_model_setting(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO settings (key, value, updated_at) "
                    "VALUES ('task_processing_model', :val, :now)"
                ),
                {
                    "val": '"gpt-4o-mini"',
                    "now": datetime.now(timezone.utc),
                },
            )
            await session.commit()

        async with factory() as session:
            config = await collect_llm_config(session)

        assert "task_processing_model" in config["models"]
        assert config["models"]["task_processing_model"]["model"] == "gpt-4o-mini"
        assert config["models"]["task_processing_model"]["category"] == "other"

        await engine.dispose()


# --- collect_health_snapshot ---


class TestCollectHealthSnapshot:
    @pytest.mark.asyncio
    async def test_with_previous_report_time(self):
        engine, factory = await _make_session_factory()

        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=6)

        # Insert a failed task after 'since'
        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, updated_at, position) "
                    "VALUES (:id, 'fail1', 'failed', :now, :updated, 0)"
                ),
                {"id": str(uuid.uuid4()), "now": now, "updated": now},
            )
            # Insert a failed task before 'since' (should be excluded)
            await session.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, updated_at, position) "
                    "VALUES (:id, 'fail2', 'failed', :now, :updated, 0)"
                ),
                {"id": str(uuid.uuid4()), "now": now, "updated": since - timedelta(hours=1)},
            )
            await session.commit()

        async with factory() as session:
            health = await collect_health_snapshot(session, since)

        assert health["task_failure_count"] == 1
        assert health["uptime_seconds"] >= 0

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_without_previous_report_counts_all(self):
        engine, factory = await _make_session_factory()

        now = datetime.now(timezone.utc)

        async with factory() as session:
            for i in range(3):
                await session.execute(
                    text(
                        "INSERT INTO tasks (id, title, status, created_at, updated_at, position) "
                        "VALUES (:id, :title, 'failed', :now, :now, 0)"
                    ),
                    {"id": str(uuid.uuid4()), "title": f"fail{i}", "now": now},
                )
            await session.commit()

        async with factory() as session:
            health = await collect_health_snapshot(session, None)

        assert health["task_failure_count"] == 3

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_no_failures(self):
        engine, factory = await _make_session_factory()

        async with factory() as session:
            health = await collect_health_snapshot(session, None)

        assert health["task_failure_count"] == 0
        assert health["uptime_seconds"] >= 0

        await engine.dispose()


# --- Full payload assembly ---


class TestPayloadAssembly:
    @pytest.mark.asyncio
    async def test_send_report_includes_all_new_sections(self):
        engine, factory = await _make_session_factory()

        reporter = TelemetryReporter(factory)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)
        mock_valkey.delete = AsyncMock()
        mock_valkey.info = AsyncMock(return_value={"redis_version": "7.2.4"})

        with patch("telemetry.httpx.AsyncClient") as mock_client_cls, \
             patch("telemetry._deployment_type", "kubernetes"), \
             patch("telemetry.get_valkey", return_value=mock_valkey), \
             patch("telemetry._cached_static_metrics", None), \
             patch("telemetry.psutil") as mock_psutil:

            mock_psutil.cpu_count.return_value = 8
            mock_psutil.virtual_memory.return_value = MagicMock(
                total=16 * 1024**3,
                available=8 * 1024**3,
            )
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await reporter._send_report()

            mock_client.post.assert_called_once()
            payload = mock_client.post.call_args[1]["json"]

            # Existing top-level fields
            assert "installation_id" in payload
            assert payload["deployment_type"] == "kubernetes"
            assert "os" in payload
            assert "arch" in payload
            assert "version" in payload
            assert "worker_count" in payload
            assert "integrations" in payload
            assert "hourly_buckets" in payload

            # New sections
            assert "system" in payload
            system = payload["system"]
            assert "cpu_count" in system
            assert "memory_total_mb" in system
            assert "memory_available_mb" in system
            assert "container_memory_limit_mb" in system
            assert "container_cpu_limit" in system
            assert "disk_available_mb" in system

            assert "infrastructure" in payload
            infra = payload["infrastructure"]
            assert "postgres_version" in infra
            assert infra["valkey_version"] == "7.2.4"
            assert infra["valkey_connected"] is True

            assert "llm" in payload
            assert "providers" in payload["llm"]
            assert "models" in payload["llm"]

            assert "health" in payload
            assert "uptime_seconds" in payload["health"]
            assert "task_failure_count" in payload["health"]

        await engine.dispose()
