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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from events import get_valkey
from models import PlatformCredential, Setting, Task

logger = logging.getLogger(__name__)

TELEMETRY_URL = "https://service.errand.cloud/api/telemetry/report"
REPORT_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
STARTUP_DELAY_SECONDS = 30  # delay before initial report
JITTER_MAX_SECONDS = 15 * 60  # up to 15 minutes of random jitter per cycle
LOCK_KEY = "errand:telemetry-lock"
LOCK_TTL = 60


# --- Deployment type detection ---

_deployment_type: str | None = None


def detect_deployment_type() -> str:
    """Auto-detect deployment type. Result is cached after first call."""
    global _deployment_type
    if _deployment_type is not None:
        return _deployment_type

    if Path("/var/run/secrets/kubernetes.io").exists():
        _deployment_type = "kubernetes"
    elif os.environ.get("APPLE_CONTAINER_RUNTIME"):
        val = os.environ["APPLE_CONTAINER_RUNTIME"].lower()
        if val == "apple":
            _deployment_type = "macos-apple"
        else:
            _deployment_type = "macos-docker"
    else:
        _deployment_type = "docker-other"

    return _deployment_type


# --- System info collection ---


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

    # Count completed (and archived, since archiving implies prior completion) tasks
    stmt = select(
        func.count(),
    ).select_from(Task).where(
        Task.status.in_(["completed", "archived"]),
    )
    if since:
        stmt = stmt.where(Task.updated_at >= since)
    # We group by hour using updated_at truncated to the hour
    # For simplicity, get all matching tasks and group in Python
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
            "pending_count": pending_count,
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
                pass
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

            system_info = collect_system_info()
            payload = {
                "installation_id": installation_id,
                "deployment_type": detect_deployment_type(),
                "integrations": integrations,
                "hourly_buckets": hourly_buckets,
                **system_info,
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(TELEMETRY_URL, json=payload)
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
