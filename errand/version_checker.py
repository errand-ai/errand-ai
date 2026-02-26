import asyncio
import logging
import os
import re

import httpx
from packaging.version import Version, InvalidVersion

logger = logging.getLogger(__name__)

GHCR_IMAGE = "errand-ai/errand"
CHECK_INTERVAL = 15 * 60  # 15 minutes

APP_VERSION = os.environ.get("APP_VERSION", "dev")

_cached_latest: str | None = None
_cached_update_available: bool = False


def _parse_version(tag: str) -> Version | None:
    try:
        return Version(tag)
    except InvalidVersion:
        return None


def _strip_pr_suffix(version_str: str) -> str:
    return re.sub(r"-pr\d+$", "", version_str)


def _is_pr_tag(tag: str) -> bool:
    return bool(re.search(r"-pr\d+$", tag))


def _find_latest_release(tags: list[str]) -> str | None:
    release_tags = [t for t in tags if not _is_pr_tag(t)]
    best: Version | None = None
    best_str: str | None = None
    for tag in release_tags:
        v = _parse_version(tag)
        if v is not None and (best is None or v > best):
            best = v
            best_str = tag
    return best_str


async def _check_ghcr() -> tuple[str | None, bool]:
    base_version = _strip_pr_suffix(APP_VERSION)
    current = _parse_version(base_version)
    if current is None:
        return None, False

    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.get(
            f"https://ghcr.io/token?scope=repository:{GHCR_IMAGE}:pull"
        )
        token_resp.raise_for_status()
        token = token_resp.json()["token"]

        tags_resp = await client.get(
            f"https://ghcr.io/v2/{GHCR_IMAGE}/tags/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        tags_resp.raise_for_status()
        tags = tags_resp.json().get("tags", [])

    latest = _find_latest_release(tags)
    if latest is None:
        return None, False

    latest_version = _parse_version(latest)
    update_available = latest_version is not None and latest_version > current
    return latest, update_available


async def run_version_checker() -> None:
    global _cached_latest, _cached_update_available
    while True:
        try:
            latest, update_available = await _check_ghcr()
            _cached_latest = latest
            _cached_update_available = update_available
            if update_available:
                logger.info("Newer version available: %s (current: %s)", latest, APP_VERSION)
        except Exception:
            logger.warning("Failed to check GHCR for latest version", exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL)


def get_version_info() -> dict:
    return {
        "current": APP_VERSION,
        "latest": _cached_latest,
        "update_available": _cached_update_available,
    }
