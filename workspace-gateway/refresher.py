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

Init mode (`python refresher.py init`, run as a Kubernetes init container before
rclone starts) uses ERRAND_API_URL / ERRAND_WORKSPACE_BEARER / WORKSPACE_PROVIDER
/ WORKSPACE_REMOTE as above, plus these two file-path vars (note they are
distinct from the gateway container's WORKSPACE_RCLONE_CONF):
  WORKSPACE_RCLONE_CONF_RO  read-only source rclone.conf to seed from
                            (default /config-ro/rclone.conf)
  WORKSPACE_CONFIG_RW       writable rclone.conf to write the fresh token into
                            (default /config-rw/rclone.conf)
"""

import json
import logging
import os
import re
import shutil
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


def _require_env(name: str) -> str:
    """Return a required env var, failing fast if unset OR empty.

    Empty values are common with compose/Helm defaults; without this the
    refresher would loop on 401s/rc errors instead of surfacing a clear
    configuration error.
    """
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(f"required env var {name} is unset or empty")
    return val


class Config:
    def __init__(self) -> None:
        self.api_url = _require_env("ERRAND_API_URL").rstrip("/")
        self.bearer = _require_env("ERRAND_WORKSPACE_BEARER")
        self.provider = _require_env("WORKSPACE_PROVIDER")
        self.remote = _require_env("WORKSPACE_REMOTE")
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


def do_refresh(cfg: Config, health: dict) -> bool:
    """Run one refresh cycle, updating `health` in place. Returns success."""
    try:
        token = fetch_access_token(cfg)
        push_token_to_rclone(cfg, token["access_token"], int(token.get("expires_at", 0)))
        health["auth_state"] = "ok"
        health["last_refresh_at"] = _now_iso()
        health["last_refresh_ok"] = True
        # Clear failure-only fields so a recovered gateway doesn't still look failing.
        health.pop("last_error", None)
        health.pop("last_attempt_at", None)
        _log("token_refreshed", provider=cfg.provider, expires_at=token.get("expires_at"))
        return True
    except Exception as exc:  # noqa: BLE001 — never crash the loop
        health["auth_state"] = "error"
        # Do NOT touch last_refresh_at — it is the last *successful* refresh time;
        # a failed attempt is represented by last_refresh_ok/last_error/last_attempt_at
        # so the health view can't look "recent" while auth is actually failing.
        health["last_attempt_at"] = _now_iso()
        health["last_refresh_ok"] = False
        health["last_error"] = str(exc)
        _log("token_refresh_failed", provider=cfg.provider, error=str(exc))
        return False


def _write_token_into_config(config_path: str, remote: str, access_token: str, expires_at: int) -> None:
    """Replace the `token` of the `[remote]` section in an rclone config file.

    Updates `access_token` (and `expiry`) in the token JSON in place, preserving
    the rest (refresh_token, token_type, etc.). Line-based to avoid mangling the
    JSON value that a naive INI parser would split on ':' / '='.
    """
    expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat() if expires_at else ""
    with open(config_path) as f:
        lines = f.read().splitlines()

    out: list[str] = []
    in_section = False
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped[1:-1] == remote
        if in_section and re.match(r"\s*token\s*=", line):
            try:
                blob = json.loads(line.split("=", 1)[1].strip())
            except Exception:
                blob = {}
            blob["access_token"] = access_token
            blob.setdefault("token_type", "Bearer")
            if expiry:
                blob["expiry"] = expiry
            line = f"token = {json.dumps(blob)}"
            replaced = True
        out.append(line)

    if not replaced:
        raise SystemExit(f"could not find a token line for remote [{remote}] in {config_path}")
    with open(config_path, "w") as f:
        f.write("\n".join(out) + "\n")


def init_config() -> None:
    """One-shot init: seed the writable rclone config with a FRESH token.

    Run as an init container before rclone starts. Copies the read-only config
    Secret to the writable path and replaces its access token with one freshly
    fetched from errand, so `rclone serve` starts authenticated even after a pod
    restart (the Secret's token may be long expired; the sidecar only refreshes
    the *running* rclone). Retries the fetch so a brief errand blip doesn't wedge
    startup — the init container is retried by Kubernetes if this ultimately fails.
    """
    cfg = Config()
    ro = os.environ.get("WORKSPACE_RCLONE_CONF_RO", "/config-ro/rclone.conf")
    rw = os.environ.get("WORKSPACE_CONFIG_RW", "/config-rw/rclone.conf")
    os.makedirs(os.path.dirname(rw), exist_ok=True)
    shutil.copyfile(ro, rw)

    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            token = fetch_access_token(cfg)
            _write_token_into_config(rw, cfg.remote, token["access_token"], int(token.get("expires_at", 0)))
            _log("init_config_ok", provider=cfg.provider, remote=cfg.remote, expires_at=token.get("expires_at"))
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _log("init_config_retry", attempt=attempt, error=str(exc))
            time.sleep(5)
    raise SystemExit(f"init_config failed after retries: {last_exc}")


def main() -> None:
    cfg = Config()
    health: dict = {"auth_state": "starting", "provider": cfg.provider}
    _log("startup", provider=cfg.provider, remote=cfg.remote, refresh_interval=cfg.refresh_interval)

    # `last_refresh` advances ONLY on a successful refresh — a failed attempt
    # (including the initial one) must be retried on the fast health-loop cadence,
    # not left unauthenticated until a full refresh interval elapses.
    last_refresh = time.monotonic() if do_refresh(cfg, health) else 0.0

    while True:
        now = time.monotonic()
        if last_refresh == 0.0 or now - last_refresh >= cfg.refresh_interval:
            if do_refresh(cfg, health):
                last_refresh = now
        health.update(read_rclone_stats(cfg))
        report_health(cfg, health)
        time.sleep(cfg.health_interval)


if __name__ == "__main__":
    # `init` mode seeds a fresh token into the config once, before rclone starts
    # (used as a Kubernetes init container); default mode is the long-running loop.
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_config()
    else:
        main()
