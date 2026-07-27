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
    silent "dirty but idle" data-loss state seen in production — a dirty entry
    pinned past the maximum dirty age by a leaked NFS handle, or a non-zero
    erroredFiles count moves write-back health to `degraded` and emits a
    structured, alertable error naming the path. It also warns when a dirty
    entry's remote fingerprint changes underneath it (the symptom of a second,
    external sync client writing the same path);
  * when an entry finishes uploading it verifies the published object's size
    against the cached data that was uploaded, so a same-length-but-wrong or
    short object is reported rather than accepted (the 2026-07-26 corruption).

The monitor must be able to see what it monitors. A cache it cannot scan is
reported `degraded` with the underlying error — never as healthy and never as
"no dirty entries" — and a one-shot self-test at startup makes a deployment in
which detection cannot run loud immediately rather than silent until a fault.

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
  WORKSPACE_FOLDER          folder within the remote being served, used to build
                            the fs for post-upload size verification (default: root)
  VFS_WRITE_BACK            gateway write-back delay, used only to derive the
                            stuck-entry grace period (default 1s)
  MAX_DIRTY_AGE_SECONDS     upper bound on how long an entry may stay dirty
                            regardless of open-handle state (default 900). NFSv3
                            has no CLOSE, so --vfs-write-back (close-triggered)
                            alone can leave an entry dirty forever.
  FORCE_FLUSH_PINNED        opt-in (default false) to attempt forcing a flush of
                            a pinned entry; reporting is the default because
                            publishing a half-written file is the failure this
                            exists to prevent
  VERIFY_UPLOAD_SIZE        verify each completed upload's size against the
                            cached data (default true; set false if the extra
                            operations/stat per upload proves costly)

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

from cache_reconcile import DirtyEntry, iter_dirty_entries, meta_root_present

# Upper bound on unresolved upload-size mismatches carried in the health report.
# A mismatch is held until its path verifies clean again, which for a path never
# rewritten is indefinite; this stops the payload growing without limit.
_MAX_TRACKED_MISMATCHES = 50

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


def _env_flag(name: str, default: bool) -> bool:
    """Parse a boolean-ish env var ('true'/'1'/'yes' vs 'false'/'0'/'no')."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


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
        # Absolute bound on dirty age, INDEPENDENT of the close-triggered
        # write-back delay: NFSv3 never closes, so a task container torn down
        # mid-mount leaves an entry in-use and never queued. Past this age an
        # entry that was never queued is reported (not force-flushed).
        self.max_dirty_age_seconds = float(os.environ.get("MAX_DIRTY_AGE_SECONDS", "900"))
        self.force_flush_pinned = _env_flag("FORCE_FLUSH_PINNED", False)
        # Post-upload integrity: the folder is needed to address the object.
        self.verify_upload_size = _env_flag("VERIFY_UPLOAD_SIZE", True)
        self.folder = os.environ.get("WORKSPACE_FOLDER", "").strip("/")
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


def read_remote_token(cfg: Config) -> dict:
    """Read the running rclone's current token blob for our remote via rc.

    Returns {} when it cannot be read — the caller must treat that as "do not
    push", never as "start from an empty token".
    """
    try:
        resp = requests.post(
            cfg.rc_url + "/config/get",
            json={"name": cfg.remote},
            timeout=cfg.rc_timeout,
        )
        resp.raise_for_status()
        raw = (resp.json() or {}).get("token")
        blob = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        return blob if isinstance(blob, dict) else {}
    except Exception as exc:  # noqa: BLE001 — caller decides what a failure means
        _log("config_get_failed", remote=cfg.remote, error=str(exc))
        return {}


def push_token_to_rclone(cfg: Config, access_token: str, expires_at: int) -> None:
    """Inject a fresh access token into the running rclone via rc config/update.

    The new access token is merged into the remote's EXISTING token blob rather
    than replacing it, because `config/update` persists what it is given and the
    blob's other fields — above all `refresh_token` — are what make the token
    refreshable without a browser.

    This is not theoretical. Sending `{access_token, token_type, expiry}` alone
    stripped `refresh_token` from the config on the first push; rclone then found
    a token it could not refresh, fell back to the interactive OAuth flow, bound
    `127.0.0.1:53682`, and sat waiting for a code that can never arrive. Every
    later `config/update` then failed with `bind: address already in use`, so
    token rotation never worked at all — observed in production 2026-07-27,
    one second after startup.

    Pushing without a refresh token is therefore refused outright: leaving the
    running rclone's in-memory token alone is strictly better than replacing a
    working config with one that forces an interactive flow.
    """
    blob = read_remote_token(cfg)
    if not blob.get("refresh_token"):
        raise RuntimeError(
            "refusing to push a token with no refresh_token for remote "
            f"'{cfg.remote}': rclone would fall back to interactive OAuth, bind "
            "127.0.0.1:53682 and break every later config/update"
        )
    blob["access_token"] = access_token
    blob.setdefault("token_type", "Bearer")
    if expires_at:
        blob["expiry"] = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    resp = requests.post(
        cfg.rc_url + "/config/update",
        json={"name": cfg.remote, "parameters": {"token": json.dumps(blob)}},
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


def _scan_dirty_entries(cache_dir: str) -> tuple[list[DirtyEntry] | None, str | None]:
    """List dirty cache entries as ``(entries, error)``.

    ``entries`` is None (not []) when the scan itself failed, with ``error``
    carrying why. The distinction is the whole point: an empty list means
    "scanned, nothing dirty", while None means "couldn't scan". Treating the
    latter as "all clear" is exactly what hid the 2026-07-26 stall — the sidecar
    could not read the root-owned cache, saw nothing, and reported healthy while
    two completed writes sat unuploaded for 24 hours.
    """
    try:
        return list(iter_dirty_entries(cache_dir)), None
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        _log("cache_scan_failed", cache_dir=cache_dir, error=error)
        return None, error


class VisibilityCheck:
    """Confirms — and keeps confirming until it can — that the monitor can see
    the cache.

    Detection that cannot run is worse than no detection, because it looks
    identical to "nothing is wrong", so this is checked explicitly rather than
    assumed. It is *not* a one-shot: both containers start together, and on a
    fresh PVC rclone has not created `vfsMeta` yet. Declaring success then would
    prove nothing — the check would pass on exactly the deployment it exists to
    catch. Until the tree has genuinely been listed the state is `pending`, and
    it is retried each health cycle. Each distinct outcome is logged once, so a
    long pending period doesn't spam.
    """

    def __init__(self) -> None:
        self.confirmed = False
        self._last_logged: str | None = None

    def check(self, cfg: Config) -> str:
        """Return 'ok', 'pending' or 'failed'; log on each change of outcome."""
        if self.confirmed:
            return "ok"
        try:
            present = meta_root_present(cfg.cache_dir)
        except OSError as exc:
            return self._report("failed", cache_dir=cfg.cache_dir, error=f"{type(exc).__name__}: {exc}",
                                detail="write-back stuck-entry detection cannot run in this deployment — "
                                       "the refresher cannot read the gateway's cache directory")
        if not present:
            return self._report("pending", cache_dir=cfg.cache_dir,
                                detail="rclone has not created the VFS metadata tree yet; "
                                       "visibility is unproven and will be rechecked")
        entries, error = _scan_dirty_entries(cfg.cache_dir)
        if entries is None:
            return self._report("failed", cache_dir=cfg.cache_dir, error=error,
                                detail="write-back stuck-entry detection cannot run in this deployment — "
                                       "the refresher cannot read the gateway's VFS cache")
        self.confirmed = True
        return self._report("ok", cache_dir=cfg.cache_dir, dirty_entries=len(entries))

    def _report(self, outcome: str, **fields) -> str:
        if outcome != self._last_logged:
            _log(f"cache_scan_selftest_{outcome}", **fields)
            self._last_logged = outcome
        return outcome


def cache_path_to_remote(cache_path: str, folder: str) -> str:
    """Map a VFS cache path to the object path relative to the served folder.

    rclone keys the cache by ``fs.Name() + "/" + fs.Root()`` (vfscache/cache.go),
    so serving ``gdrive:Errand`` caches ``notes/a.txt`` at
    ``gdrive{…}/Errand/notes/a.txt`` — the served folder **is** part of the cache
    path. Stripping only the leading identity component leaves the folder
    duplicated in the resulting reference (``gdrive:Errand/Errand/notes/a.txt``),
    which resolves to nothing, so every verification would silently come back
    "unverified" — detection that cannot run, looking exactly like nothing wrong.

    ``Root()`` equals the configured folder for a direct remote, which is what
    both supported providers use. (The reconcile resolves paths against a real
    listing instead, because it also has to cope with an alias remote expanding
    to its backend and absolute path — and because a wrong answer there strands
    or destroys data, where a wrong answer here only degrades to "unverified".)
    """
    parts = cache_path.replace(os.sep, "/").split("/")
    depth = 1 + len([c for c in folder.split("/") if c])
    return "/".join(parts[depth:])


def stat_remote_object(cfg: Config, cache_path: str) -> dict | None:
    """Stat the cloud object behind a cache path via rc `operations/stat`.

    Used to verify a completed upload. Returns None when the object is absent or
    the call fails (both mean "unverified", never "verified OK").
    """
    rel = cache_path_to_remote(cache_path, cfg.folder)
    if not rel:
        return None
    fs = f"{cfg.remote}:{cfg.folder}" if cfg.folder else f"{cfg.remote}:"
    try:
        resp = requests.post(
            cfg.rc_url + "/operations/stat",
            json={"fs": fs, "remote": rel},
            timeout=cfg.rc_timeout,
        )
        resp.raise_for_status()
        item = resp.json().get("item")
        return item if isinstance(item, dict) else None
    except Exception as exc:  # noqa: BLE001 — verification is best-effort
        _log("upload_verify_stat_failed", path=cache_path, error=str(exc))
        return None


class WriteBackMonitor:
    """Tracks write-back health across health cycles.

    Combines the aggregate `vfs/stats` upload counters with a per-path scan of
    the persistent VFS cache, because the production data-loss state — a dirty
    entry that is never queued (`uploadsQueued:0, erroredFiles:0`) — is invisible
    to `vfs/stats` alone and only observable by inspecting the cache metadata.

    A dirty entry is a fault when it stays dirty past the grace period without
    progressing. An orphaned dirty entry (no data to upload) is stuck the moment
    it ages out — nothing can ever upload it. A dirty-with-data entry is judged
    against the *global* upload queue: `vfs/stats` exposes no per-path progress,
    so an entry is flagged once it ages past the grace period while the queue is
    known idle. Because a busy queue (uploading unrelated files) could otherwise
    mask a single non-progressing entry indefinitely, an absolute overdue backstop
    flags any entry dirty past `max(10 × grace, 300s)` regardless of queue state.
    An entry that is *still* dirty past the configured maximum dirty age having
    never been seen queued is reported as pinned by an open handle — NFSv3 has no
    CLOSE, so a task container torn down mid-mount leaves the entry permanently
    in-use and the close-triggered write-back timer never fires. A non-zero
    `erroredFiles` count is degraded regardless of age. All surface a structured,
    alertable error naming the path(s). The monitor also warns when a dirty
    entry's remote fingerprint changes underneath it — the symptom of a second,
    external sync client writing the same path.

    Finally, when an entry stops being dirty (its upload completed) the monitor
    verifies the published object's size against the cached data that was
    uploaded. The 2026-07-26 corruption published an object of exactly the
    expected byte count made of new-over-stale bytes, so size equality is a floor,
    not a proof — but a short or over-long object is caught outright, and the
    check is what turns "rclone said it uploaded" into evidence.
    """

    def __init__(self, cfg: Config, clock=time.monotonic, verifier=None) -> None:
        self._grace = cfg.stuck_grace_seconds
        # Absolute backstop: past this age a dirty entry is flagged even if the
        # global upload queue is busy, so unrelated uploads can't mask it forever.
        self._overdue = max(10.0 * cfg.stuck_grace_seconds, 300.0)
        self._max_dirty_age = cfg.max_dirty_age_seconds
        self._force_flush = cfg.force_flush_pinned
        # Injected `(path, expected_size) -> remote item dict | None`; None
        # disables post-upload verification entirely (VERIFY_UPLOAD_SIZE=false).
        self._verifier = verifier
        self._clock = clock
        # Per-path state carried across cycles.
        self._first_seen_dirty: dict[str, float] = {}
        self._fingerprints: dict[str, object] = {}
        # Whether the upload queue was ever observed non-idle while this path was
        # dirty. `vfs/stats` has no per-path view, so this over-attributes global
        # activity to the path — deliberately, since the error direction is
        # "don't claim pinned when it might have been queued".
        self._ever_queued: dict[str, bool] = {}
        # Last observed cached data size per dirty path, used to verify the
        # object published once the entry goes clean, plus whether that length
        # has settled (seen twice unchanged) — a mid-write sample is not a
        # length worth comparing anything against.
        self._last_data_size: dict[str, int] = {}
        self._size_stable: dict[str, bool] = {}
        # Verified-bad uploads, kept until the path verifies clean again so a
        # persistent mismatch stays degraded rather than flashing once.
        self._size_mismatches: dict[str, dict] = {}
        # (path, reason) degraded conditions already logged, so a persistent
        # fault is logged once per episode rather than every health cycle.
        self._logged_degraded: set = set()
        self._force_flush_warned = False

    def evaluate(self, vfs_stats: dict, dirty_entries: list[DirtyEntry]) -> dict:
        """Return a write-back health block; update per-path state in place.

        Deterministic given its inputs — rc stats, the scanned entries, the
        injected clock and the injected verifier — so it can be exercised
        exhaustively in tests without an rclone. The verifier is the only I/O it
        performs, and only for paths that just stopped being dirty.
        """
        now = self._clock()
        current = {e.path: e for e in dirty_entries}

        # Paths that were dirty and no longer are: their upload completed (or
        # they were reconciled away). Verify what actually got published BEFORE
        # dropping the cached size we need to compare against.
        for path in list(self._first_seen_dirty):
            if path not in current:
                self._verify_completed_upload(path)
                self._first_seen_dirty.pop(path, None)
                self._fingerprints.pop(path, None)
                self._ever_queued.pop(path, None)
                self._last_data_size.pop(path, None)
                self._size_stable.pop(path, None)

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

        for path, entry in sorted(current.items()):  # deterministic log/error order
            first_seen = self._first_seen_dirty.setdefault(path, now)
            age = now - first_seen
            oldest_age = max(oldest_age, age)
            # Remember the cached length while we can still read it; once the
            # entry goes clean the data file may be evicted and there would be
            # nothing left to verify the published object against.
            #
            # Only a length we have seen TWICE unchanged is eligible: the cache
            # file grows as the NFS client writes, so a single sample taken
            # mid-write is a partial length. Comparing that against the (correct,
            # complete) published object would report a mismatch on a perfectly
            # good upload — a false alarm on the one signal that has to be
            # trustworthy. An unstable entry is left unverified instead.
            if entry.data_size is not None:
                self._size_stable[path] = self._last_data_size.get(path) == entry.data_size
                self._last_data_size[path] = entry.data_size
            if queue_state_known and not queue_idle:
                self._ever_queued[path] = True

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
            # Past grace. Classify why it's stuck, most-specific first:
            #   * orphan (no data) can never upload → stuck regardless of queue;
            #   * pinned → dirty past the absolute maximum dirty age having never
            #     been seen queued: the leaked-NFS-handle case, where a
            #     close-triggered write-back timer will never fire at all;
            #   * queue *known* idle → nothing is progressing (never flag on an
            #     unknown queue during an rc outage — that's a false positive);
            #   * overdue → aged past the absolute backstop, so a busy queue
            #     uploading unrelated files can't mask it indefinitely.
            if entry.is_orphaned:
                reason = "orphaned_dirty_entry"
            elif age >= self._max_dirty_age and not self._ever_queued.get(path):
                reason = "dirty_entry_pinned_by_handle"
            elif queue_idle:
                reason = "dirty_entry_not_progressing"
            elif age >= self._overdue:
                reason = "dirty_entry_overdue"
            else:
                continue
            stuck_paths.append(path)
            err = {"path": path, "reason": reason, "dirty_age_seconds": round(age, 1)}
            if reason == "dirty_entry_pinned_by_handle":
                err["max_dirty_age_seconds"] = round(self._max_dirty_age, 1)
                err["detail"] = (
                    "dirty past the maximum dirty age and never queued — the entry is held "
                    "open (NFSv3 has no CLOSE), so the close-triggered write-back never fires"
                )
                self._note_force_flush(path)
            errors.append(err)

        # Verified-bad uploads persist until the path verifies clean again.
        errors.extend(self._size_mismatches[p] for p in sorted(self._size_mismatches))

        if errored > 0:
            err = {"reason": "errored_uploads", "errored_files": errored}
            # vfs/stats reports only a count, not the errored paths. Surface the
            # currently-dirty entries as candidates so the alert has something to
            # point at (the errored file is almost certainly among them).
            if current:
                err["candidate_paths"] = sorted(current)
            errors.append(err)

        degraded = bool(stuck_paths) or errored > 0 or bool(self._size_mismatches)
        self._emit_degraded(errors)

        return {
            "write_back_state": "degraded" if degraded else "ok",
            "write_back": {
                "uploads_queued": vfs_stats.get("uploads_queued"),
                "uploads_in_progress": vfs_stats.get("uploads_in_progress"),
                "errored_files": vfs_stats.get("errored_files"),
                "dirty_entries": len(current),
                # Sorted so the payload/alerting is stable regardless of the
                # os.walk order the cache scan produced.
                "stuck_entries": sorted(stuck_paths),
                "size_mismatches": sorted(self._size_mismatches),
                "oldest_dirty_age_seconds": round(oldest_age, 1),
                "grace_seconds": round(self._grace, 1),
                "max_dirty_age_seconds": round(self._max_dirty_age, 1),
            },
            "write_back_errors": errors,
        }

    def _note_force_flush(self, path: str) -> None:
        """Handle the opt-in force-flush request for a pinned entry.

        Reporting is the required behaviour; forcing is opt-in and off by
        default. rclone's rc API exposes no way to flush a *dirty but never
        queued* VFS item — `vfs/queue-set-expiry` only reorders items already in
        the queue — so when forcing is requested we say so plainly rather than
        reaching around the VFS to publish a file a client may still be writing,
        which is precisely the torn-write failure this change exists to prevent.
        """
        if not self._force_flush or self._force_flush_warned:
            return
        self._force_flush_warned = True
        _log(
            "force_flush_unavailable",
            path=path,
            detail="FORCE_FLUSH_PINNED is enabled but rclone's rc API offers no safe way to "
                   "flush a dirty, never-queued VFS item; the entry is reported instead. "
                   "Recover it via the runbook.",
        )

    def _verify_completed_upload(self, path: str) -> None:
        """Compare the published object's size against the cached data uploaded.

        Called when a path stops being dirty. A mismatch is recorded (and stays
        recorded until the path verifies clean) so that a bad publish is
        degraded, alertable, and named — the 2026-07-26 corruption reported
        success and was never contradicted by anything rclone exposed.

        An object we cannot stat is *unverified*, not failed: the file may simply
        have been deleted through the mount, and turning that into an alert would
        make the check noise rather than signal.
        """
        expected = self._last_data_size.get(path)
        if self._verifier is None or expected is None:
            return
        if not self._size_stable.get(path):
            # Only ever sampled mid-write; we don't know the final length, so we
            # have nothing trustworthy to compare against.
            _log("upload_unverified", path=path, reason="cached_size_never_settled")
            return
        item = self._verifier(path, expected)
        if not item:
            _log("upload_unverified", path=path, expected_size=expected)
            return
        actual = item.get("Size")
        if actual == expected:
            if self._size_mismatches.pop(path, None) is not None:
                _log("upload_size_verified", path=path, size=actual)
            return
        self._size_mismatches[path] = {
            "path": path,
            "reason": "upload_size_mismatch",
            "expected_size": expected,
            "published_size": actual,
            "detail": "the published object does not match the cached data that was uploaded; "
                      "the local copy is retained in the cache PVC for recovery",
        }
        # Bounded: a mismatch is held until the path verifies clean again, which
        # for a path never rewritten is forever. Cap the set so a pathological
        # run cannot grow the health payload without limit; the oldest is dropped
        # and said so, rather than silently.
        while len(self._size_mismatches) > _MAX_TRACKED_MISMATCHES:
            dropped, _ = next(iter(self._size_mismatches.items()))
            self._size_mismatches.pop(dropped)
            _log("upload_size_mismatch_dropped", path=dropped,
                 detail=f"more than {_MAX_TRACKED_MISMATCHES} unresolved mismatches tracked")

    def scan_unavailable(self, vfs_stats: dict, error: str | None = None) -> dict:
        """Health block for a cycle where the cache scan failed.

        A failed scan is a *fault of the monitor itself*, not "all clear": an
        unreadable cache is reported degraded with the underlying error, never as
        healthy and never as an absence of dirty entries. It must also NOT reset
        per-path age/fingerprint state — doing so would restart a stuck entry's
        clock and mask it.
        """
        err = {"reason": "cache_scan_failed"}
        if error:
            err["error"] = error
        errors = [err]
        self._emit_degraded(errors)
        return {
            "write_back_state": "degraded",
            "write_back": {
                "uploads_queued": vfs_stats.get("uploads_queued"),
                "uploads_in_progress": vfs_stats.get("uploads_in_progress"),
                "errored_files": vfs_stats.get("errored_files"),
                "dirty_entries": None,   # unknown — scan failed
                "stuck_entries": [],
                "grace_seconds": round(self._grace, 1),
                "max_dirty_age_seconds": round(self._max_dirty_age, 1),
            },
            "write_back_errors": errors,
        }

    def _emit_degraded(self, errors: list[dict]) -> None:
        """Log each degraded condition only on transition (when it first appears).

        A persistent fault re-evaluated every ~30s must not spam the logs; a
        condition that clears drops out of the tracked set, so a later recurrence
        logs again.
        """
        current_keys = {(e.get("path"), e["reason"]) for e in errors}
        for err in errors:
            if (err.get("path"), err["reason"]) not in self._logged_degraded:
                _log("write_back_degraded", **err)
        self._logged_degraded = current_keys


def collect_health_stats(cfg: Config, monitor: WriteBackMonitor) -> dict:
    """One health-cycle read: rc upload stats + write-back health from the cache."""
    stats = read_vfs_stats(cfg)
    dirty, scan_error = _scan_dirty_entries(cfg.cache_dir)
    # None == scan failed (distinct from an empty list): don't feed it to
    # evaluate(), which would treat "no entries" as "all clean" and reset state.
    if dirty is None:
        stats.update(monitor.scan_unavailable(stats, scan_error))
    else:
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
    verifier = (lambda path, expected: stat_remote_object(cfg, path)) if cfg.verify_upload_size else None
    monitor = WriteBackMonitor(cfg, verifier=verifier)
    _log(
        "startup",
        provider=cfg.provider,
        remote=cfg.remote,
        refresh_interval=cfg.refresh_interval,
        cache_dir=cfg.cache_dir,
        stuck_grace_seconds=cfg.stuck_grace_seconds,
        max_dirty_age_seconds=cfg.max_dirty_age_seconds,
        verify_upload_size=cfg.verify_upload_size,
        force_flush_pinned=cfg.force_flush_pinned,
    )
    # Prove the monitor can see the cache before anything depends on it. A
    # deployment where this fails is one where stuck-entry detection cannot run
    # at all — the condition that made the 2026-07-26 stall invisible. Retried
    # on the health cadence until it is genuinely proven (on a fresh cache
    # rclone has not created the metadata tree yet, and "nothing there" is not
    # evidence of visibility).
    visibility = VisibilityCheck()
    visibility.check(cfg)

    # `last_refresh` advances ONLY on a successful refresh — a failed attempt
    # (including the initial one) must be retried on the fast health-loop cadence,
    # not left unauthenticated until a full refresh interval elapses.
    last_refresh = time.monotonic() if do_refresh(cfg, health) else 0.0

    while True:
        now = time.monotonic()
        if last_refresh == 0.0 or now - last_refresh >= cfg.refresh_interval:
            if do_refresh(cfg, health):
                last_refresh = now
        visibility.check(cfg)
        health.update(collect_health_stats(cfg, monitor))
        health["cache_visibility"] = "ok" if visibility.confirmed else "unproven"
        report_health(cfg, health)
        time.sleep(cfg.health_interval)


if __name__ == "__main__":
    # `init` mode seeds a fresh token into the config once, before rclone starts
    # (used as a Kubernetes init container); default mode is the long-running loop.
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_config()
    else:
        main()
