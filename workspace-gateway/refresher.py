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
    sync breakage is never silent;
  * on the same cadence it monitors write-back health: it reads `vfs/stats`
    (uploadsQueued/uploadsInProgress/erroredFiles) and scans the persistent VFS
    cache for dirty entries. A dirty entry that stays dirty past a grace period
    without making progress (nothing queued/uploading, no errored retry) — the
    silent "dirty but idle" data-loss state seen in production — or a non-zero
    erroredFiles count moves write-back health to `degraded` and emits a
    structured, alertable error naming the path. It also warns when a dirty
    entry's remote fingerprint changes underneath it (the symptom of a second,
    external sync client writing the same path).

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
  WORKSPACE_CACHE_DIR       persistent VFS cache dir to scan for dirty entries
                            (default /cache); mounted read-only into the sidecar
  VFS_WRITE_BACK            gateway write-back delay, used only to derive the
                            stuck-entry grace period (default 1s)

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

from cache_reconcile import DirtyEntry, iter_dirty_entries

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


_DURATION_UNITS = (("ms", 0.001), ("s", 1.0), ("m", 60.0), ("h", 3600.0))


def _parse_duration(text: str, default_seconds: float = 1.0) -> float:
    """Parse an rclone-style duration ('1s', '500ms', '2m', '1h') to seconds.

    Falls back to ``default_seconds`` on anything unrecognised — this only feeds
    the derived grace period, so a bad value must not crash the sidecar.
    """
    text = (text or "").strip().lower()
    for suffix, scale in _DURATION_UNITS:  # 'ms' before 's' so it wins
        if text.endswith(suffix):
            try:
                return float(text[: -len(suffix)]) * scale
            except ValueError:
                return default_seconds
    try:
        return float(text)  # bare number = seconds
    except ValueError:
        return default_seconds


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
        # Persistent VFS cache dir, scanned (read-only) for stuck dirty entries.
        self.cache_dir = os.environ.get("WORKSPACE_CACHE_DIR", "/cache")
        # Grace period before a still-dirty entry is treated as stuck: derived
        # from the gateway's write-back delay and floored at 30s so normal upload
        # latency can't flap health. Mirrors the gateway's VFS_WRITE_BACK default.
        self.write_back_seconds = _parse_duration(os.environ.get("VFS_WRITE_BACK", "1s"), 1.0)
        self.stuck_grace_seconds = max(3.0 * self.write_back_seconds, 30.0)
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


def read_vfs_stats(cfg: Config) -> dict:
    """Read the rclone rc `vfs/stats` diskCache counters. Best-effort.

    Returns a dict with `pending_uploads` (queued + in progress) and the raw
    `uploads_queued` / `uploads_in_progress` / `errored_files` counters, or all
    None when the rc call fails (so callers can tell "no data" from "zero").
    """
    stats = {
        "pending_uploads": None,
        "uploads_queued": None,
        "uploads_in_progress": None,
        "errored_files": None,
    }
    try:
        resp = requests.post(cfg.rc_url + "/vfs/stats", timeout=cfg.rc_timeout)
        resp.raise_for_status()
        disk = resp.json().get("diskCache") or {}
        queued = int(disk.get("uploadsQueued", 0) or 0)
        in_progress = int(disk.get("uploadsInProgress", 0) or 0)
        errored = int(disk.get("erroredFiles", 0) or 0)
        stats.update(
            pending_uploads=queued + in_progress,
            uploads_queued=queued,
            uploads_in_progress=in_progress,
            errored_files=errored,
        )
    except Exception as exc:  # noqa: BLE001 — health is best-effort
        _log("rc_stats_failed", error=str(exc))
    return stats


def _scan_dirty_entries(cache_dir: str) -> list[DirtyEntry]:
    """List dirty cache entries, swallowing scan errors (health is best-effort)."""
    try:
        return list(iter_dirty_entries(cache_dir))
    except Exception as exc:  # noqa: BLE001
        _log("cache_scan_failed", cache_dir=cache_dir, error=str(exc))
        return []


class WriteBackMonitor:
    """Tracks write-back health across health cycles.

    Combines the aggregate `vfs/stats` upload counters with a per-path scan of
    the persistent VFS cache, because the production data-loss state — a dirty
    entry that is never queued (`uploadsQueued:0, erroredFiles:0`) — is invisible
    to `vfs/stats` alone and only observable by inspecting the cache metadata.

    A dirty entry is a fault when it stays dirty past the grace period without
    progressing (nothing queued/uploading for it). An orphaned dirty entry (no
    data to upload) is stuck the moment it ages out — nothing can ever upload it.
    A non-zero `erroredFiles` count is degraded regardless of age. Both surface a
    structured, alertable error naming the path(s). The monitor also warns when a
    dirty entry's remote fingerprint changes underneath it — the symptom of a
    second, external sync client writing the same path.
    """

    def __init__(self, cfg: Config, clock=time.monotonic) -> None:
        self._grace = cfg.stuck_grace_seconds
        self._clock = clock
        # Per-path state carried across cycles.
        self._first_seen_dirty: dict[str, float] = {}
        self._fingerprints: dict[str, object] = {}
        # (path, reason) degraded conditions already logged, so a persistent
        # fault is logged once per episode rather than every health cycle.
        self._logged_degraded: set = set()

    def evaluate(self, vfs_stats: dict, dirty_entries: list[DirtyEntry]) -> dict:
        """Return a write-back health block; update per-path state in place.

        Pure w.r.t. its arguments (rc stats + scanned entries + injected clock),
        so it can be exercised deterministically in tests.
        """
        now = self._clock()
        current = {e.path: e for e in dirty_entries}

        # Forget paths that are no longer dirty (uploaded or reconciled away).
        for path in list(self._first_seen_dirty):
            if path not in current:
                self._first_seen_dirty.pop(path, None)
                self._fingerprints.pop(path, None)

        queued = vfs_stats.get("uploads_queued")
        in_progress = vfs_stats.get("uploads_in_progress")
        errored = vfs_stats.get("errored_files") or 0
        # Distinguish "queue is known idle" from "queue state unknown" (an rc
        # outage returns None): coercing unknown to idle would falsely flag a
        # dirty-with-data entry as stuck during a transient rc failure.
        queue_state_known = queued is not None and in_progress is not None
        queue_idle = queue_state_known and (queued + in_progress) == 0

        errors: list[dict] = []
        stuck_paths: list[str] = []
        oldest_age = 0.0

        for path, entry in current.items():
            first_seen = self._first_seen_dirty.setdefault(path, now)
            age = now - first_seen
            oldest_age = max(oldest_age, age)

            # Concurrent-writer signal: fingerprint changed while locally dirty.
            prev_fp = self._fingerprints.get(path, entry.fingerprint)
            if path in self._fingerprints and entry.fingerprint != prev_fp:
                _log(
                    "concurrent_writer_detected",
                    path=path,
                    previous_fingerprint=prev_fp,
                    remote_fingerprint=entry.fingerprint,
                    detail="remote fingerprint changed under a locally-dirty entry — a second sync client may be writing this path",
                )
            self._fingerprints[path] = entry.fingerprint

            if age < self._grace:
                continue
            # Past grace. An orphan (no data) can never upload → stuck regardless
            # of queue state. A dirty-with-data entry is stuck only when the queue
            # is *known* idle — never when the queue state is merely unknown
            # (rc outage), which would otherwise be a false positive.
            if entry.is_orphaned or queue_idle:
                stuck_paths.append(path)
                errors.append({
                    "path": path,
                    "reason": "orphaned_dirty_entry" if entry.is_orphaned else "dirty_entry_not_progressing",
                    "dirty_age_seconds": round(age, 1),
                })

        if errored > 0:
            err = {"reason": "errored_uploads", "errored_files": errored}
            # vfs/stats reports only a count, not the errored paths. Surface the
            # currently-dirty entries as candidates so the alert has something to
            # point at (the errored file is almost certainly among them).
            if current:
                err["candidate_paths"] = sorted(current)
            errors.append(err)

        degraded = bool(stuck_paths) or errored > 0

        # Log each degraded condition only on transition — when it first appears
        # — not every health cycle: a persistent stuck entry (re-evaluated every
        # ~30s) must not spam the logs. A condition that clears drops out of the
        # set, so a later recurrence logs again.
        current_keys = {(e.get("path"), e["reason"]) for e in errors}
        for err in errors:
            if (err.get("path"), err["reason"]) not in self._logged_degraded:
                _log("write_back_degraded", **err)
        self._logged_degraded = current_keys

        return {
            "write_back_state": "degraded" if degraded else "ok",
            "write_back": {
                "uploads_queued": vfs_stats.get("uploads_queued"),
                "uploads_in_progress": vfs_stats.get("uploads_in_progress"),
                "errored_files": vfs_stats.get("errored_files"),
                "dirty_entries": len(current),
                "stuck_entries": stuck_paths,
                "oldest_dirty_age_seconds": round(oldest_age, 1),
                "grace_seconds": round(self._grace, 1),
            },
            "write_back_errors": errors,
        }


def collect_health_stats(cfg: Config, monitor: WriteBackMonitor) -> dict:
    """One health-cycle read: rc upload stats + write-back health from the cache."""
    stats = read_vfs_stats(cfg)
    dirty = _scan_dirty_entries(cfg.cache_dir)
    stats.update(monitor.evaluate(stats, dirty))
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
    monitor = WriteBackMonitor(cfg)
    _log(
        "startup",
        provider=cfg.provider,
        remote=cfg.remote,
        refresh_interval=cfg.refresh_interval,
        cache_dir=cfg.cache_dir,
        stuck_grace_seconds=cfg.stuck_grace_seconds,
    )

    # `last_refresh` advances ONLY on a successful refresh — a failed attempt
    # (including the initial one) must be retried on the fast health-loop cadence,
    # not left unauthenticated until a full refresh interval elapses.
    last_refresh = time.monotonic() if do_refresh(cfg, health) else 0.0

    while True:
        now = time.monotonic()
        if last_refresh == 0.0 or now - last_refresh >= cfg.refresh_interval:
            if do_refresh(cfg, health):
                last_refresh = now
        health.update(collect_health_stats(cfg, monitor))
        report_health(cfg, health)
        time.sleep(cfg.health_interval)


if __name__ == "__main__":
    # `init` mode seeds a fresh token into the config once, before rclone starts
    # (used as a Kubernetes init container); default mode is the long-running loop.
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_config()
    else:
        main()
