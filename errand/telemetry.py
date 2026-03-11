"""Usage telemetry: collect anonymous metrics and report to errand-cloud.

The reporter runs in the errand-server process (not the worker) and uses a
Valkey distributed lock so only one replica reports per cycle — the same
pattern as the scheduler and zombie cleanup.
"""

import asyncio
import logging
import os
import platform
import random
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from events import get_valkey
from models import LlmProvider, PlatformCredential, Setting, Task

logger = logging.getLogger(__name__)

_process_start_time = time.monotonic()

TELEMETRY_URL = "https://service.errand.cloud/api/telemetry/report"
REPORT_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
STARTUP_DELAY_SECONDS = 30  # delay before initial report
JITTER_MAX_SECONDS = 15 * 60  # up to 15 minutes of random jitter per cycle
LOCK_KEY = "errand:telemetry-lock"
LOCK_TTL = 60


# --- Deployment type detection ---

_deployment_type: str | None = None


def detect_deployment_type() -> str:
    """Auto-detect deployment type. Result is cached after first call.

    Priority:
    1. Kubernetes secrets path → "kubernetes"
    2. ERRAND_CONTAINER_RUNTIME env var → use its value directly
       (e.g. "apple-container", "apple-docker", "windows-docker", "linux-docker")
    3. Default → "unknown-docker"
    """
    global _deployment_type
    if _deployment_type is not None:
        return _deployment_type

    if Path("/var/run/secrets/kubernetes.io").exists():
        _deployment_type = "kubernetes"
    elif os.environ.get("ERRAND_CONTAINER_RUNTIME"):
        _deployment_type = os.environ["ERRAND_CONTAINER_RUNTIME"]
    else:
        _deployment_type = "unknown-docker"

    return _deployment_type


# --- System info collection ---

_cached_static_metrics: dict[str, Any] | None = None


def _read_cgroup_memory_limit() -> int | None:
    """Detect container memory limit from cgroup v2/v1 files. Returns MB or None."""
    # Try cgroup v2
    try:
        value = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if value == "max":
            return None
        return int(value) // (1024 * 1024)
    except (FileNotFoundError, OSError, ValueError):
        pass

    # Try cgroup v1
    try:
        value = int(Path("/sys/fs/cgroup/memory/memory.limit_in_bytes").read_text().strip())
        total = psutil.virtual_memory().total
        if value < total:
            return value // (1024 * 1024)
        return None
    except (FileNotFoundError, OSError, ValueError):
        pass

    return None


def _read_cgroup_cpu_limit() -> float | None:
    """Detect container CPU limit from cgroup v2/v1 files. Returns float or None."""
    # Try cgroup v2
    try:
        content = Path("/sys/fs/cgroup/cpu.max").read_text().strip()
        parts = content.split()
        if parts[0] == "max":
            return None
        quota = int(parts[0])
        period = int(parts[1])
        return quota / period
    except (FileNotFoundError, OSError, ValueError, IndexError):
        pass  # v2 cgroup files not present or unreadable — try v1

    # Try cgroup v1
    try:
        quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip())
        if quota == -1:
            return None
        try:
            period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip())
        except (FileNotFoundError, OSError, ValueError):
            period = 100000
        return quota / period
    except (FileNotFoundError, OSError, ValueError):
        pass  # v1 cgroup files not present — not running in a container

    return None


def collect_system_metrics() -> dict[str, Any]:
    """Collect system metrics. Static values are cached after first call."""
    global _cached_static_metrics

    if _cached_static_metrics is None:
        _cached_static_metrics = {
            "cpu_count": psutil.cpu_count(logical=True),
            "memory_total_mb": psutil.virtual_memory().total // (1024 * 1024),
            "container_memory_limit_mb": _read_cgroup_memory_limit(),
            "container_cpu_limit": _read_cgroup_cpu_limit(),
        }

    # Dynamic values — re-read each cycle
    return {
        **_cached_static_metrics,
        "memory_available_mb": psutil.virtual_memory().available // (1024 * 1024),
        "disk_available_mb": psutil.disk_usage("/").free // (1024 * 1024),
    }


def collect_system_info(worker_count: int = 1) -> dict[str, Any]:
    """Collect static system information for telemetry reports."""
    version = ""
    version_path = Path(__file__).parent.parent / "VERSION"
    if version_path.exists():
        version = version_path.read_text().strip()

    return {
        "os": platform.system().lower(),
        "arch": platform.machine(),
        "version": version,
        "worker_count": worker_count,
    }


# --- Infrastructure info collection ---


async def collect_postgres_version(session: AsyncSession) -> str | None:
    """Execute SELECT version() and parse the PostgreSQL version string."""
    try:
        from sqlalchemy import text
        result = await session.execute(text("SELECT version()"))
        row = result.scalar_one_or_none()
        if row:
            # Format: "PostgreSQL 16.2 on ..."
            parts = row.split()
            if len(parts) >= 2:
                return parts[1]
        return None
    except Exception:
        logger.warning("Failed to collect PostgreSQL version", exc_info=True)
        return None


async def collect_valkey_info() -> tuple[str | None, bool]:
    """Query Valkey INFO server for version. Returns (version, connected)."""
    valkey = get_valkey()
    if valkey is None:
        return None, False

    try:
        info = await valkey.info("server")
        version = info.get("redis_version")
        return version, True
    except Exception:
        logger.warning("Failed to query Valkey INFO", exc_info=True)
        return None, True


# --- LLM config collection ---


def classify_provider_url(base_url: str, provider_type: str) -> str:
    """Classify a provider base URL into a category without exposing the raw URL."""
    url_lower = base_url.lower()

    if "api.openai.com" in url_lower:
        return "openai"
    if "api.anthropic.com" in url_lower:
        return "anthropic"
    if "generativelanguage.googleapis.com" in url_lower:
        return "gemini"
    if "api.x.ai" in url_lower:
        return "xai"
    if "localhost:11434" in url_lower or "127.0.0.1:11434" in url_lower:
        return "ollama"

    if provider_type == "litellm":
        return "litellm-other"
    if provider_type == "openai_compatible":
        return "openai-compatible-other"
    return "other"


async def collect_llm_config(session: AsyncSession) -> dict[str, Any]:
    """Collect LLM provider categories and model settings for telemetry."""
    # Collect providers
    result = await session.execute(
        select(LlmProvider.provider_type, LlmProvider.base_url, LlmProvider.id)
    )
    provider_rows = result.all()

    providers = []
    provider_categories: dict[str, str] = {}  # provider_id -> category
    for provider_type, base_url, provider_id in provider_rows:
        category = classify_provider_url(base_url, provider_type)
        providers.append({"type": provider_type, "category": category})
        provider_categories[str(provider_id)] = category

    # Collect model settings
    model_setting_keys = ["llm_model", "task_processing_model", "transcription_model"]
    result = await session.execute(
        select(Setting).where(Setting.key.in_(model_setting_keys))
    )
    settings = result.scalars().all()

    models: dict[str, dict[str, str]] = {}
    for setting in settings:
        val = setting.value
        provider_id = None
        model_name: str | None = None

        if isinstance(val, dict):
            provider_id = val.get("provider_id")
            model_name = val.get("model")
        elif isinstance(val, str):
            model_name = val
        else:
            continue

        if not model_name:
            continue
        category = provider_categories.get(str(provider_id), "other") if provider_id else "other"
        models[setting.key] = {"category": category, "model": model_name}

    return {"providers": providers, "models": models}


# --- Health snapshot collection ---


async def collect_health_snapshot(
    session: AsyncSession, since: datetime | None
) -> dict[str, Any]:
    """Collect health metrics: uptime and task failure count."""
    uptime_seconds = int(time.monotonic() - _process_start_time)

    # Count failed tasks since last report
    stmt = select(func.count()).select_from(Task).where(Task.status == "failed")
    if since is not None:
        stmt = stmt.where(Task.updated_at > since)
    result = await session.execute(stmt)
    failure_count = result.scalar() or 0

    return {
        "uptime_seconds": uptime_seconds,
        "task_failure_count": failure_count,
    }


# --- Valkey distributed lock ---


async def _acquire_telemetry_lock() -> bool:
    valkey = get_valkey()
    if valkey is None:
        return False
    lock_value = f"telemetry-{socket.gethostname()}"
    result = await valkey.set(LOCK_KEY, lock_value, nx=True, ex=LOCK_TTL)
    if result:
        return True
    current = await valkey.get(LOCK_KEY)
    if current == lock_value:
        await valkey.expire(LOCK_KEY, LOCK_TTL)
        return True
    return False


async def _release_telemetry_lock() -> None:
    valkey = get_valkey()
    if valkey is None:
        return
    try:
        await valkey.delete(LOCK_KEY)
    except Exception:
        logger.warning("Failed to release telemetry lock", exc_info=True)


# --- Installation ID ---


async def get_or_create_installation_id(session: AsyncSession) -> str:
    """Get or generate the installation UUID."""
    result = await session.execute(
        select(Setting).where(Setting.key == "telemetry_installation_id")
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        return setting.value if isinstance(setting.value, str) else str(setting.value)

    installation_id = str(uuid.uuid4())
    session.add(Setting(key="telemetry_installation_id", value=installation_id))
    await session.commit()
    return installation_id


# --- Active integrations ---


async def collect_active_integrations(session: AsyncSession) -> list[str]:
    """Query connected platform integrations."""
    result = await session.execute(
        select(PlatformCredential.platform_id).where(
            PlatformCredential.status == "connected"
        )
    )
    return [row[0] for row in result.all()]


# --- Metrics collection from database ---


async def _get_last_report_time(session: AsyncSession) -> datetime | None:
    result = await session.execute(
        select(Setting).where(Setting.key == "telemetry_last_report_at")
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        try:
            return datetime.fromisoformat(setting.value)
        except (ValueError, TypeError):
            return None
    return None


async def _set_last_report_time(session: AsyncSession, dt: datetime) -> None:
    result = await session.execute(
        select(Setting).where(Setting.key == "telemetry_last_report_at")
    )
    setting = result.scalar_one_or_none()
    val = dt.isoformat()
    if setting:
        setting.value = val
    else:
        session.add(Setting(key="telemetry_last_report_at", value=val))
    await session.commit()


async def collect_hourly_metrics(
    session: AsyncSession, since: datetime | None
) -> list[dict[str, Any]]:
    """Query completed tasks since `since`, grouped by hour."""
    now = datetime.now(timezone.utc)

    # Get completed/archived tasks and group by hour in Python
    task_stmt = select(Task.updated_at).where(
        Task.status.in_(["completed", "archived"]),
    )
    if since:
        task_stmt = task_stmt.where(Task.updated_at >= since)
    result = await session.execute(task_stmt)
    rows = result.all()

    # Group by hour
    hourly: dict[str, int] = {}
    for (updated_at,) in rows:
        if updated_at is None:
            continue
        hour_key = updated_at.strftime("%Y-%m-%dT%H:00:00Z")
        hourly[hour_key] = hourly.get(hour_key, 0) + 1

    # If no tasks completed, still report the current hour with zero
    if not hourly:
        hour_key = now.strftime("%Y-%m-%dT%H:00:00Z")
        hourly[hour_key] = 0

    # Get current pending and scheduled counts (point-in-time snapshots)
    pending_result = await session.execute(
        select(func.count()).select_from(Task).where(Task.status == "pending")
    )
    pending_count = pending_result.scalar() or 0

    scheduled_result = await session.execute(
        select(func.count()).select_from(Task).where(Task.status == "scheduled")
    )
    scheduled_count = scheduled_result.scalar() or 0

    return [
        {
            "hour": hour,
            "tasks_completed": count,
            "tasks_scheduled": scheduled_count,
            "max_pending": pending_count,
        }
        for hour, count in sorted(hourly.items())
    ]


# --- Telemetry reporter ---


class TelemetryReporter:
    """Periodic telemetry reporter that runs as an asyncio background task in the server."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self._task = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Expected during shutdown
            except Exception:
                logger.warning("Error while stopping telemetry reporter task", exc_info=True)
        await _release_telemetry_lock()

    async def _run_loop(self) -> None:
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        try:
            await self._send_report()
        except Exception:
            logger.warning("Telemetry startup report failed", exc_info=True)

        while True:
            jitter = random.randint(0, JITTER_MAX_SECONDS)
            await asyncio.sleep(REPORT_INTERVAL_SECONDS + jitter)
            try:
                await self._send_report()
            except Exception:
                logger.warning("Telemetry report failed", exc_info=True)

    async def _send_report(self) -> None:
        # Check enabled before acquiring lock
        async with self.session_factory() as session:
            enabled = await self._is_enabled(session)
            if not enabled:
                return

        # Acquire Valkey lock — only one server replica reports
        locked = await _acquire_telemetry_lock()
        if not locked:
            logger.debug("Telemetry lock held by another replica, skipping cycle")
            return

        try:
            async with self.session_factory() as session:
                installation_id = await get_or_create_installation_id(session)
                integrations = await collect_active_integrations(session)
                last_report = await _get_last_report_time(session)
                hourly_buckets = await collect_hourly_metrics(session, last_report)
                postgres_version = await collect_postgres_version(session)
                llm_config = await collect_llm_config(session)
                health = await collect_health_snapshot(session, last_report)

            valkey_version, valkey_connected = await collect_valkey_info()

            system_info = collect_system_info()
            system_metrics = collect_system_metrics()
            payload = {
                "installation_id": installation_id,
                "deployment_type": detect_deployment_type(),
                "integrations": integrations,
                "hourly_buckets": hourly_buckets,
                **system_info,
                "system": system_metrics,
                "infrastructure": {
                    "postgres_version": postgres_version,
                    "valkey_version": valkey_version,
                    "valkey_connected": valkey_connected,
                },
                "llm": llm_config,
                "health": health,
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(TELEMETRY_URL, json=payload)
                if resp.status_code >= 400:
                    logger.warning(
                        "Telemetry POST returned %d: %s",
                        resp.status_code,
                        resp.text[:500],
                    )
                resp.raise_for_status()

            # Success — update last report time
            async with self.session_factory() as session:
                await _set_last_report_time(session, datetime.now(timezone.utc))
            logger.info("Telemetry report sent successfully")
        except Exception:
            logger.warning("Telemetry report failed, will retry next cycle")
        finally:
            await _release_telemetry_lock()

    async def _is_enabled(self, session: AsyncSession) -> bool:
        """Check if telemetry is enabled (env var takes precedence)."""
        env_val = os.environ.get("TELEMETRY_ENABLED")
        if env_val is not None:
            return env_val.lower() not in ("false", "0", "no")

        result = await session.execute(
            select(Setting).where(Setting.key == "telemetry_enabled")
        )
        setting = result.scalar_one_or_none()
        if setting is not None:
            val = setting.value
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() not in ("false", "0", "no")
            return bool(val)

        return True  # Default enabled
