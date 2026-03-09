"""Usage telemetry: collect anonymous metrics and report to errand-cloud."""

import asyncio
import json
import logging
import os
import platform
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PlatformCredential, Setting

logger = logging.getLogger(__name__)

TELEMETRY_URL = "https://cloud.errand.ai/api/telemetry/report"
REPORT_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
STARTUP_DELAY_SECONDS = 30  # delay before initial report
JITTER_MAX_SECONDS = 15 * 60  # up to 15 minutes of random jitter per cycle


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
        _deployment_type = "macos-desktop"
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


# --- Hourly bucket accumulator ---


class TelemetryBuckets:
    """In-memory hourly bucket accumulator for usage metrics."""

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, int]] = {}
        self.enabled: bool = True

    def _current_hour(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")

    def _ensure_bucket(self, hour: str) -> dict[str, int]:
        if hour not in self._buckets:
            self._buckets[hour] = {
                "tasks_completed": 0,
                "tasks_scheduled": 0,
                "max_pending": 0,
            }
        return self._buckets[hour]

    def increment_completed(self) -> None:
        if not self.enabled:
            return
        bucket = self._ensure_bucket(self._current_hour())
        bucket["tasks_completed"] += 1

    def update_max_pending(self, current_size: int) -> None:
        if not self.enabled:
            return
        bucket = self._ensure_bucket(self._current_hour())
        if current_size > bucket["max_pending"]:
            bucket["max_pending"] = current_size

    def set_tasks_scheduled(self, count: int) -> None:
        """Set the scheduled count on all pending buckets at report time."""
        for bucket in self._buckets.values():
            bucket["tasks_scheduled"] = count

    def get_and_clear(self) -> list[dict[str, Any]]:
        """Return all buckets as a list and clear them."""
        result = [
            {"hour": hour, **data}
            for hour, data in sorted(self._buckets.items())
        ]
        self._buckets.clear()
        return result

    def is_empty(self) -> bool:
        return len(self._buckets) == 0

    def to_json(self) -> str:
        return json.dumps(self._buckets)

    def load_from_json(self, data: str) -> None:
        """Load buckets from JSON, merging with any existing data."""
        loaded = json.loads(data)
        for hour, values in loaded.items():
            if hour in self._buckets:
                existing = self._buckets[hour]
                existing["tasks_completed"] += values.get("tasks_completed", 0)
                existing["max_pending"] = max(
                    existing["max_pending"], values.get("max_pending", 0)
                )
            else:
                self._buckets[hour] = values


# --- Database persistence ---


async def save_buckets_to_db(session: AsyncSession, buckets: TelemetryBuckets) -> None:
    """Persist unsent buckets to the settings table."""
    result = await session.execute(
        select(Setting).where(Setting.key == "telemetry_pending_buckets")
    )
    setting = result.scalar_one_or_none()
    data = buckets.to_json()

    if setting:
        setting.value = data
    else:
        session.add(Setting(key="telemetry_pending_buckets", value=data))
    await session.commit()


async def load_buckets_from_db(session: AsyncSession, buckets: TelemetryBuckets) -> None:
    """Load persisted buckets from the settings table."""
    result = await session.execute(
        select(Setting).where(Setting.key == "telemetry_pending_buckets")
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        data = setting.value if isinstance(setting.value, str) else json.dumps(setting.value)
        buckets.load_from_json(data)


async def clear_buckets_in_db(session: AsyncSession) -> None:
    """Clear persisted buckets after successful send."""
    result = await session.execute(
        select(Setting).where(Setting.key == "telemetry_pending_buckets")
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = "{}"
        await session.commit()


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


# --- Telemetry reporter ---


class TelemetryReporter:
    """Periodic telemetry reporter that runs as an asyncio background task."""

    def __init__(self, buckets: TelemetryBuckets, session_factory, worker_count: int = 1) -> None:
        self.buckets = buckets
        self.session_factory = session_factory
        self.worker_count = worker_count
        self._task = None

    async def start(self) -> None:
        """Start the background reporting task. Also loads persisted buckets and syncs enabled flag."""
        async with self.session_factory() as session:
            self.buckets.enabled = await self._is_enabled(session)
            await load_buckets_from_db(session, self.buckets)

        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the reporter and persist pending buckets."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Expected during shutdown
            except Exception:
                logger.warning("Error while stopping telemetry reporter task", exc_info=True)

        if not self.buckets.is_empty():
            async with self.session_factory() as session:
                await save_buckets_to_db(session, self.buckets)

    async def _run_loop(self) -> None:
        # Send an initial "alive" report shortly after startup
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        try:
            await self._send_report()
        except Exception:
            logger.warning("Telemetry startup report failed", exc_info=True)

        # Then report every 6 hours with random jitter to spread load
        while True:
            jitter = random.randint(0, JITTER_MAX_SECONDS)
            await asyncio.sleep(REPORT_INTERVAL_SECONDS + jitter)
            try:
                await self._send_report()
            except Exception:
                logger.warning("Telemetry report failed", exc_info=True)

    async def _send_report(self) -> None:
        async with self.session_factory() as session:
            # Sync the enabled flag so accumulation stops/starts between cycles
            enabled = await self._is_enabled(session)
            self.buckets.enabled = enabled
            if not enabled:
                return

            # Persist buckets before attempting send
            await save_buckets_to_db(session, self.buckets)

            # Collect data
            installation_id = await get_or_create_installation_id(session)
            integrations = await collect_active_integrations(session)

            # Set scheduled count on all buckets
            from sqlalchemy import func
            from models import Task

            result = await session.execute(
                select(func.count()).select_from(Task).where(Task.status == "scheduled")
            )
            scheduled_count = result.scalar() or 0
            self.buckets.set_tasks_scheduled(scheduled_count)

        system_info = collect_system_info(self.worker_count)
        hourly_buckets = self.buckets.get_and_clear()

        payload = {
            "installation_id": installation_id,
            "deployment_type": detect_deployment_type(),
            "integrations": integrations,
            "hourly_buckets": hourly_buckets,
            **system_info,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(TELEMETRY_URL, json=payload)
                resp.raise_for_status()
            # Success — clear persisted buckets
            async with self.session_factory() as session:
                await clear_buckets_in_db(session)
            logger.info("Telemetry report sent successfully")
        except Exception:
            # Retain buckets for next cycle by reloading what we cleared
            for bucket_data in hourly_buckets:
                hour = bucket_data["hour"]
                self.buckets._ensure_bucket(hour)
                self.buckets._buckets[hour]["tasks_completed"] += bucket_data["tasks_completed"]
                self.buckets._buckets[hour]["max_pending"] = max(
                    self.buckets._buckets[hour]["max_pending"],
                    bucket_data["max_pending"],
                )
                self.buckets._buckets[hour]["tasks_scheduled"] = bucket_data["tasks_scheduled"]
            logger.warning("Telemetry report failed, buckets retained for next cycle")

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
