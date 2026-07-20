#!/usr/bin/env python3
"""Token-refresher sidecar for the shared-workspace gateway.

`rclone serve` is long-running, but the cloud access tokens it uses expire after
~60 minutes and are refreshed by errand (via errand-cloud). This sidecar keeps
the running rclone authenticated without restarting the NFS server:

  * on start and every ~50 minutes, it fetches a fresh access token from the
    errand server's refresh endpoint using the workspace-scoped bearer, then
    pushes it into the running rclone via the rc API (`config/update`) with the
    token passed explicitly (finding F4: a bare update triggers interactive
    OAuth; the rc call is timeout-guarded because it can block under throttling);
  * periodically it reads rclone's vfs/core stats and reports gateway health
    (last refresh, auth state, pending uploads) back to the errand server, so
    sync breakage is never silent.

All failures are logged as single-line structured JSON and reflected in the
health report; rclone keeps retrying queued operations regardless.

Environment:
  ERRAND_API_URL            errand server base URL (required)
  ERRAND_WORKSPACE_BEARER   workspace-scoped bearer for the refresh endpoints (required)
  WORKSPACE_PROVIDER        "google_drive" or "onedrive" (required)
  WORKSPACE_REMOTE          rclone remote name to update (required)
  RCLONE_RC_URL             rclone rc base URL (default http://127.0.0.1:5572)
  REFRESH_INTERVAL_SECONDS  seconds between refreshes (default 3000 = 50 min)
  HEALTH_INTERVAL_SECONDS   seconds between health reports (default 30)
  RC_TIMEOUT_SECONDS        per rc call timeout (default 20)
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
logger = logging.getLogger("workspace-refresher")

_PROVIDER_REFRESH_PATH = {
    "google_drive": "/api/google/refresh-token",
    "onedrive": "/api/onedrive/refresh-token",
}


def _log(event: str, **fields) -> None:
    """Emit one structured JSON log line."""
    logger.info(json.dumps({"component": "workspace-refresher", "event": event, **fields}))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Config:
    def __init__(self) -> None:
        self.api_url = os.environ["ERRAND_API_URL"].rstrip("/")
        self.bearer = os.environ["ERRAND_WORKSPACE_BEARER"]
        self.provider = os.environ["WORKSPACE_PROVIDER"]
        self.remote = os.environ["WORKSPACE_REMOTE"]
        self.rc_url = os.environ.get("RCLONE_RC_URL", "http://127.0.0.1:5572").rstrip("/")
        self.refresh_interval = int(os.environ.get("REFRESH_INTERVAL_SECONDS", "3000"))
        self.health_interval = int(os.environ.get("HEALTH_INTERVAL_SECONDS", "30"))
        self.rc_timeout = int(os.environ.get("RC_TIMEOUT_SECONDS", "20"))
        if self.provider not in _PROVIDER_REFRESH_PATH:
            raise SystemExit(f"unsupported WORKSPACE_PROVIDER: {self.provider}")


def fetch_access_token(cfg: Config) -> dict:
    """Fetch a fresh access token from the errand refresh endpoint.

    Returns {"access_token": str, "expires_at": int}. Raises on failure.
    """
    url = cfg.api_url + _PROVIDER_REFRESH_PATH[cfg.provider]
    resp = requests.post(url, headers={"Authorization": f"Bearer {cfg.bearer}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def push_token_to_rclone(cfg: Config, access_token: str, expires_at: int) -> None:
    """Inject the access token into the running rclone via rc config/update.

    The token is passed explicitly as the `token` parameter so rclone never
    attempts an interactive OAuth flow. Guarded by a timeout because a
    config/update can block re-initialising the backend under API throttling.
    """
    expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat() if expires_at else ""
    token_blob = {"access_token": access_token, "token_type": "Bearer"}
    if expiry:
        token_blob["expiry"] = expiry
    resp = requests.post(
        cfg.rc_url + "/config/update",
        json={"name": cfg.remote, "parameters": {"token": json.dumps(token_blob)}},
        timeout=cfg.rc_timeout,
    )
    resp.raise_for_status()


def read_rclone_stats(cfg: Config) -> dict:
    """Read pending-upload / poll stats from rclone rc. Best-effort."""
    stats = {"pending_uploads": None}
    try:
        resp = requests.post(cfg.rc_url + "/vfs/stats", timeout=cfg.rc_timeout)
        resp.raise_for_status()
        data = resp.json()
        disk = data.get("diskCache") or {}
        # 'uploadsQueued' + 'uploadsInProgress' when present.
        queued = disk.get("uploadsQueued", 0) or 0
        in_progress = disk.get("uploadsInProgress", 0) or 0
        stats["pending_uploads"] = int(queued) + int(in_progress)
    except Exception as exc:  # noqa: BLE001 — health is best-effort
        _log("rc_stats_failed", error=str(exc))
    return stats


def report_health(cfg: Config, health: dict) -> None:
    """Report gateway health back to the errand server. Best-effort."""
    try:
        resp = requests.post(
            cfg.api_url + "/api/workspace/health",
            headers={"Authorization": f"Bearer {cfg.bearer}"},
            json=health,
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        _log("health_report_failed", error=str(exc))


def do_refresh(cfg: Config, health: dict) -> None:
    """Run one refresh cycle, updating `health` in place."""
    try:
        token = fetch_access_token(cfg)
        push_token_to_rclone(cfg, token["access_token"], int(token.get("expires_at", 0)))
        health["auth_state"] = "ok"
        health["last_refresh_at"] = _now_iso()
        health["last_refresh_ok"] = True
        _log("token_refreshed", provider=cfg.provider, expires_at=token.get("expires_at"))
    except Exception as exc:  # noqa: BLE001 — never crash the loop
        health["auth_state"] = "error"
        health["last_refresh_at"] = _now_iso()
        health["last_refresh_ok"] = False
        health["last_error"] = str(exc)
        _log("token_refresh_failed", provider=cfg.provider, error=str(exc))


def main() -> None:
    cfg = Config()
    health: dict = {"auth_state": "starting", "provider": cfg.provider}
    _log("startup", provider=cfg.provider, remote=cfg.remote, refresh_interval=cfg.refresh_interval)

    do_refresh(cfg, health)  # refresh immediately on start
    last_refresh = time.monotonic()

    while True:
        now = time.monotonic()
        if now - last_refresh >= cfg.refresh_interval:
            do_refresh(cfg, health)
            last_refresh = now
        health.update(read_rclone_stats(cfg))
        report_health(cfg, health)
        time.sleep(cfg.health_interval)


if __name__ == "__main__":
    main()
