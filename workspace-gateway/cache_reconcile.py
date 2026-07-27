#!/usr/bin/env python3
"""Reconcile faulted dirty entries in the rclone VFS cache before serving.

Run once by the gateway entrypoint, *before* `rclone serve` starts, over the
persistent `--vfs-cache-mode full` cache directory.

Background (the incidents this closes)
--------------------------------------
A completed write goes: task `close()` → rclone marks the VFS item dirty and
writes its data into the cache → write-back uploads it. Two faulted shapes have
been observed in production, both of which leave a dirty entry that must not be
uploaded as-is:

**1. Orphaned (2026-07-25) — dirty with no data to upload**::

    vfsMeta/<remote>/.../BlogsToProcess.md : {"Dirty": true, "Size": 0, "Rs": null}
    vfs/<remote>/.../BlogsToProcess.md      : (missing)

rclone recorded a dirty change, lost the data backing it, and never queued an
upload. There is nothing to send; left in place the entry can block
change-polling or upload an empty file over the good cloud copy. Resolution:
clear the stale meta so the next serve+poll re-fetches the cloud object.

**2. Desynced (2026-07-26) — dirty with data, but metadata says empty**::

    vfsMeta/<remote>/.../BlogsToProcess.md : {"Dirty": true, "Size": 0, "Rs": null}
    vfs/<remote>/.../BlogsToProcess.md      : 56254 bytes PRESENT

The metadata disagrees with the data file. Previously this was classified as "a
resumable upload; leave it" — after which rclone published a **partial write**:
new content over the head of a stale buffer, old tail retained, a line broken
mid-word, and the resulting cloud object the same length as before. Resolution:
**repair, never delete** — the data file may hold the only copy of completed
work (it did: 22 lines of task output). Metadata `Size`/`Rs` are corrected to
match the data file and the entry is left dirty so the *complete* content
uploads.

Repair is only safe while the gateway is the sole writer. If the entry's
recorded remote fingerprint no longer matches the cloud object, the local
content is not a safe successor to the remote, so the entry is **quarantined**
(moved aside within the cache PVC, content retained) instead of uploaded. The
same applies when the remote cannot be checked at all: a stalled-but-reported
write is recoverable, a torn published write may not be.

Every action is logged as one structured JSON line. The scan is best-effort at
the `main()` boundary (a reconcile failure must not stop the gateway serving),
but it never *silently* does nothing: an unreadable cache raises rather than
walking zero entries, so "blind" can never look like "clean".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Iterator, NamedTuple

# rclone lays the VFS cache out as two parallel trees under the cache dir:
#   <cache_dir>/vfs/<remote>/<path>      — the cached file data
#   <cache_dir>/vfsMeta/<remote>/<path>  — per-item JSON metadata (Dirty, Size, …)
_DATA_SUBDIR = "vfs"
_META_SUBDIR = "vfsMeta"
# Quarantine lives beside them (NOT inside either), so rclone never sees a
# quarantined item as cache content. The cache layout is mirrored underneath so
# an operator recovers content by its familiar path; `manifest.jsonl` records
# why each entry was quarantined. Documented in docs/workspace-gateway-runbook.md.
_QUARANTINE_SUBDIR = "quarantine"
_QUARANTINE_MANIFEST = "manifest.jsonl"


class DirtyEntry(NamedTuple):
    """A cache entry marked dirty (not-yet-uploaded) in its VFS metadata."""

    path: str                # cache-relative path, e.g. "<remote>/dir/file"
    meta: dict               # parsed item metadata (Dirty, Size, Fingerprint, …)
    data_path: str           # absolute path to the sibling data file (may not exist)
    has_data: bool           # True if a data file backs the entry (any length)
    data_size: int | None = None  # data file length; None if absent/unstattable

    @property
    def fingerprint(self):
        return self.meta.get("Fingerprint")

    @property
    def meta_size(self):
        return self.meta.get("Size")

    @property
    def is_orphaned(self) -> bool:
        """Dirty but with no data file backing it — the 2026-07-25 terminal,
        silent data-loss state (dirty meta, ``Size: 0``, no ``vfs/`` file).

        Orphaned means the data file is *absent*. A data file that exists is
        preserved even when zero-length: that is a legitimate empty-file write
        (a task creating/truncating a file to empty), not a lost upload, and must
        not be discarded. rclone uploads it like any other cached write.
        """
        return not self.has_data

    @property
    def is_inconsistent(self) -> bool:
        """Metadata disagrees with the data file — the 2026-07-26 corruption
        signature: ``Size: 0`` and no read ranges (``Rs: null``) while a
        non-empty data file is present.

        Deliberately narrow. A zero-length data file with ``Size: 0`` is a
        consistent empty write, and an entry with read ranges recorded is a
        genuinely resumable partial download — neither is this fault. Uploading
        from this state is what produced a corrupted cloud object.
        """
        if not self.has_data or not self.data_size:
            return False
        return not self.meta.get("Size") and not self.meta.get("Rs")


def _log(event: str, **fields) -> None:
    """Emit one structured JSON log line (matches the refresher's format)."""
    print(json.dumps({"component": "workspace-gateway", "event": event, **fields}), file=sys.stderr)


def _is_dirty(meta: dict) -> bool:
    """True if the item metadata marks the entry dirty (not-yet-uploaded)."""
    return bool(meta.get("Dirty"))


def _stat_data_file(data_path: str) -> tuple[bool, int | None]:
    """Return ``(present, size)`` for a cache data file.

    Presence — not size — decides orphanhood. A zero-length data file that EXISTS
    is a legitimate empty-file write and must be preserved; only a genuinely
    ABSENT data file counts as "no data". If the path can't be stat'd for any
    reason other than 'missing' (permissions, transient I/O), we assume it is
    present with an unknown size: misclassifying a still-backed entry as orphaned
    would delete a real write, which is exactly the data loss this exists to
    prevent. An unknown size also suppresses the inconsistency check, so we never
    repair metadata against a length we could not read.
    """
    try:
        return True, os.stat(data_path).st_size
    except FileNotFoundError:
        return False, None
    except OSError:
        return True, None


def _raise_walk_error(exc: OSError) -> None:
    """os.walk error handler that propagates instead of skipping.

    This is load-bearing. os.walk's default is to *ignore* an unreadable
    directory, which made an unreadable cache yield zero entries — the scanner
    reported "nothing dirty, healthy" while two files sat dirty and unuploaded
    for 24 hours. A scan that cannot see the cache must fail loudly so callers
    can report it as degraded (see refresher.scan_unavailable), never return an
    empty result that is indistinguishable from a clean cache.
    """
    raise exc


def iter_dirty_entries(cache_dir: str) -> Iterator[DirtyEntry]:
    """Yield every dirty entry in the VFS cache under ``cache_dir``.

    Shared by the startup reconcile (which repairs/quarantines faulted ones) and
    the refresher's write-back health scan (which tracks dirty age, size and
    fingerprints). Non-dirty entries are ordinary read cache and are skipped.
    Individual meta files that are unreadable or not JSON are skipped rather than
    guessed at — but a directory that cannot be *listed* raises ``OSError``,
    because that means the scan is blind rather than finding nothing.
    """
    meta_root = os.path.join(cache_dir, _META_SUBDIR)
    data_root = os.path.join(cache_dir, _DATA_SUBDIR)
    if not os.path.isdir(meta_root):
        return
    # Probe readability up front: os.walk on an unlistable root would otherwise
    # yield nothing at all, silently. This turns it into an OSError immediately.
    os.listdir(meta_root)
    for dirpath, _dirs, files in os.walk(meta_root, onerror=_raise_walk_error):
        for name in files:
            meta_path = os.path.join(dirpath, name)
            rel = os.path.relpath(meta_path, meta_root)
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict) or not _is_dirty(meta):
                continue
            data_path = os.path.join(data_root, rel)
            present, size = _stat_data_file(data_path)
            yield DirtyEntry(
                path=rel,
                meta=meta,
                data_path=data_path,
                has_data=present,
                data_size=size,
            )


# --- Remote fingerprint verification -----------------------------------------
#
# Repairing an inconsistent entry means publishing the cached content over the
# cloud object. That is only safe if the cloud object is still the one the entry
# was derived from. rclone records that as a "fingerprint": "<size>,<modtime>,
# <hash>" (e.g. "63805,2026-07-26T19:28:15Z,2bbf85b7…"). We re-stat the remote
# and compare. Any doubt → quarantine, never upload.


def parse_fingerprint(fingerprint) -> tuple[int | None, str | None, str | None]:
    """Split an rclone fingerprint into ``(size, modtime, hash)``.

    Components are positional and optional in rclone's own format, so anything
    unparseable yields ``None`` for that component (and therefore no match).
    """
    if not isinstance(fingerprint, str) or not fingerprint:
        return None, None, None
    parts = fingerprint.split(",")
    try:
        size = int(parts[0])
    except (ValueError, IndexError):
        size = None
    modtime = parts[1] if len(parts) > 1 else None
    hashval = parts[2] if len(parts) > 2 else None
    return size, modtime, hashval


def _parse_time(text) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def fingerprint_matches(fingerprint, remote: dict | None, *, modtime_tolerance: float = 1.0) -> bool:
    """True when the recorded fingerprint still describes the current remote object.

    ``remote`` is an ``rclone lsjson --stat`` record (``Size``/``ModTime``/
    ``Hashes``) or None when the remote could not be read. Conservative by
    construction: an unreadable remote, an unparseable fingerprint, or a missing
    comparable component all return False, which routes the entry to quarantine
    rather than to an upload we cannot justify.
    """
    if not remote:
        return False
    size, modtime, hashval = parse_fingerprint(fingerprint)
    if size is None:
        return False
    if size != remote.get("Size"):
        return False
    # Hash is the strongest available signal; when both sides have one it decides.
    remote_hashes = {k.lower(): v for k, v in (remote.get("Hashes") or {}).items()}
    if hashval:
        if hashval.lower() in {str(v).lower() for v in remote_hashes.values()}:
            return True
        if remote_hashes:
            return False  # remote published hashes and none matched → moved on
    # No usable hash on one side: fall back to size + modtime (within tolerance,
    # since providers round modtimes differently from rclone's recorded value).
    recorded_at, remote_at = _parse_time(modtime), _parse_time(remote.get("ModTime"))
    if recorded_at is None or remote_at is None:
        return False
    return abs((recorded_at - remote_at).total_seconds()) <= modtime_tolerance


# Probe outcomes. "absent" and "error" are deliberately distinct: an object that
# demonstrably does not exist remotely cannot be overwritten by uploading the
# cached copy, whereas an object we simply could not look up might be anything.
FOUND, ABSENT, ERROR = "found", "absent", "error"


class RcloneRemoteProbe:
    """Resolves the cloud object behind a cache path, via the `rclone` binary.

    The reconcile runs *before* `rclone serve` starts, so the rc API is not yet
    listening — we shell out to the same rclone binary and config instead.

    Path mapping is the subtle part. A cache path is **not**
    ``<remote>/<path-below-the-serve-root>``: rclone keys the cache by the fs's
    identity *and its full root*, so serving ``gdrive:Errand`` caches
    ``Errand/notes/a.txt`` at ``vfs/gdrive{…}/Errand/notes/a.txt``, and an alias
    remote expands to its underlying backend and absolute path
    (``loc:Errand`` → ``vfs/local/tmp/data/Errand/…``, verified against rclone
    1.68). The depth of that prefix therefore cannot be derived from the target
    string. Instead we list the serve root once — lazily, only if something
    actually needs verifying — and match each cache path by its longest suffix
    that names a real object. The listing is also what lets us distinguish
    "not there" from "couldn't look".
    """

    def __init__(self, target: str, *, rclone: str = "rclone", timeout: float = 120.0, attempts: int = 3):
        self.target = target.rstrip("/")
        self.rclone = rclone
        self.timeout = timeout
        self.attempts = attempts
        self._index: dict[str, dict] | None = None
        self._index_failed = False

    def _load_index(self) -> bool:
        """List every object under the serve root once. Returns success."""
        if self._index is not None:
            return True
        if self._index_failed:
            return False
        last_error = None
        for attempt in range(1, self.attempts + 1):
            try:
                proc = subprocess.run(
                    [self.rclone, "lsjson", "-R", "--files-only", "--hash", self.target],
                    capture_output=True, text=True, timeout=self.timeout,
                )
                if proc.returncode == 0:
                    listing = json.loads(proc.stdout or "[]")
                    self._index = {
                        item["Path"].replace(os.sep, "/"): item
                        for item in listing
                        if isinstance(item, dict) and item.get("Path")
                    }
                    _log("remote_index_loaded", target=self.target, objects=len(self._index))
                    return True
                last_error = (proc.stderr or "").strip()[:400]
            except Exception as exc:  # noqa: BLE001 — probe failures are data, not crashes
                last_error = str(exc)
            _log("remote_index_retry", target=self.target, attempt=attempt, error=last_error)
        _log("remote_index_failed", target=self.target, error=last_error)
        self._index_failed = True
        return False

    def lookup(self, cache_path: str) -> tuple[str, dict | None]:
        """Resolve a cache path to ``(FOUND|ABSENT|ERROR, item)``.

        Matches the longest suffix of the cache path that names a real object,
        which strips the fs-root prefix without having to know its depth.
        """
        if not self._load_index():
            return ERROR, None
        parts = cache_path.replace(os.sep, "/").split("/")
        # Start after the first component (always the fs identity dir) and give
        # up the last one (the filename itself must remain).
        for start in range(1, len(parts)):
            item = self._index.get("/".join(parts[start:]))
            if item is not None:
                return FOUND, item
        return ABSENT, None


# --- Repair / quarantine ------------------------------------------------------


def repair_metadata(cache_dir: str, entry: DirtyEntry) -> dict:
    """Rewrite an inconsistent entry's metadata to match its data file.

    ``Size`` is set to the data file's actual length and ``Rs`` to the single
    full extent, leaving ``Dirty`` true so rclone uploads the *complete* cached
    content. The data file is never touched — it may be the only copy.
    """
    meta_path = os.path.join(cache_dir, _META_SUBDIR, entry.path)
    repaired = dict(entry.meta)
    repaired["Size"] = entry.data_size
    repaired["Rs"] = [{"Pos": 0, "Size": entry.data_size}]
    # Write via a temp file + rename so a crash mid-repair can never leave
    # truncated metadata behind (which would be a worse desync than we started with).
    tmp_path = meta_path + ".repair.tmp"
    with open(tmp_path, "w") as f:
        json.dump(repaired, f)
    os.replace(tmp_path, meta_path)
    return {
        "path": entry.path,
        "action": "repaired_desynced_meta",
        "meta_size": entry.meta_size,
        "data_size": entry.data_size,
    }


def _quarantine_destination(quarantine_root: str, subdir: str, rel: str) -> str:
    """Collision-safe destination under the quarantine tree (`…`, `….1`, `….2`)."""
    dest = os.path.join(quarantine_root, subdir, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if not os.path.exists(dest):
        return dest
    n = 1
    while os.path.exists(f"{dest}.{n}"):
        n += 1
    return f"{dest}.{n}"


def quarantine_entry(cache_dir: str, entry: DirtyEntry, reason: str, **detail) -> dict:
    """Move a faulted entry aside within the cache PVC, retaining its content.

    Both the data file and its metadata move under ``<cache_dir>/quarantine/``,
    mirroring the cache layout, and a line is appended to the quarantine
    manifest. Nothing is deleted: quarantined content is retained for manual
    recovery (see docs/workspace-gateway-runbook.md).
    """
    quarantine_root = os.path.join(cache_dir, _QUARANTINE_SUBDIR)
    meta_path = os.path.join(cache_dir, _META_SUBDIR, entry.path)
    moved: list[str] = []
    # Data first, then meta: if we crash between the two, the remaining meta is
    # an orphan — a state the existing orphan path already handles safely.
    for src, subdir in ((entry.data_path, _DATA_SUBDIR), (meta_path, _META_SUBDIR)):
        try:
            dest = _quarantine_destination(quarantine_root, subdir, entry.path)
            shutil.move(src, dest)
            moved.append(os.path.relpath(dest, cache_dir))
        except FileNotFoundError:
            pass
        except OSError as exc:
            _log("quarantine_move_failed", path=f"{subdir}/{entry.path}", error=str(exc))
    record = {
        "path": entry.path,
        "action": "quarantined",
        "reason": reason,
        "meta_size": entry.meta_size,
        "data_size": entry.data_size,
        "quarantined_to": moved,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        **detail,
    }
    try:
        os.makedirs(quarantine_root, exist_ok=True)
        with open(os.path.join(quarantine_root, _QUARANTINE_MANIFEST), "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        _log("quarantine_manifest_failed", path=entry.path, error=str(exc))
    return record


def _clear_orphan(cache_dir: str, entry: DirtyEntry) -> dict | None:
    """Remove an orphaned dirty entry's stale meta (and empty data file, if any).

    Returns the reconciliation record, or None if the meta could not actually be
    cleared (in which case the orphan is still present and must not be counted).
    """
    meta_path = os.path.join(cache_dir, _META_SUBDIR, entry.path)
    removed: list[str] = []
    # Clearing the meta is what actually reconciles the orphan (it stops rclone
    # acting on the phantom dirty entry). Remove the data file first (if any),
    # then the meta, so a crash mid-reconcile never leaves data without its meta.
    meta_cleared = True
    for target, label, is_meta in (
        (entry.data_path, _DATA_SUBDIR, False),
        (meta_path, _META_SUBDIR, True),
    ):
        try:
            os.remove(target)
            removed.append(f"{label}/{entry.path}")
        except FileNotFoundError:
            # Already absent (e.g. an orphan with no data file) — nothing to
            # remove for this side; not an error, so stay quiet.
            pass
        except OSError as exc:
            # A real removal failure (permissions, busy). Log why, and if it was
            # the META that failed, the orphan is NOT actually cleared.
            _log("orphaned_dirty_entry_remove_failed", path=f"{label}/{entry.path}", error=str(exc))
            if is_meta:
                meta_cleared = False
    if not meta_cleared:
        # Left in place (still dirty): surfaced via the remove_failed log above;
        # excluded from the reconciled set so the count stays truthful.
        return None
    return {
        "path": entry.path,
        "action": "cleared_orphaned_dirty_meta",
        "meta_size": entry.meta_size,
        "removed": removed,
    }


def reconcile_cache(cache_dir: str, probe=None) -> list[dict]:
    """Reconcile faulted dirty entries in the VFS cache under ``cache_dir``.

    Three dispositions, one record per entry acted on:

    * **orphaned** (dirty, no data file) → stale meta cleared, so the next
      serve+poll re-fetches the cloud object instead of acting on a phantom write.
    * **inconsistent** (dirty, data present, ``Size: 0``/``Rs: null``) → metadata
      **repaired** to match the data file when the recorded remote fingerprint
      still matches the cloud object, so the complete content uploads.
    * **inconsistent with a moved (or unreadable) remote** → **quarantined**:
      content retained aside, nothing published. Uploading here would overwrite a
      newer remote object with a stale local one.

    A dirty entry with consistent metadata and data is a genuinely resumable
    upload and is left for ``rclone serve`` to finish. Non-dirty entries are
    ordinary read cache and are left alone. ``probe`` supplies the remote stat
    (``RcloneRemoteProbe`` in production, a fake in tests); without one, an
    inconsistent entry cannot be verified and is quarantined.
    """
    reconciled: list[dict] = []
    # Sort by cache-relative path so the reconciled list and per-entry logs are
    # deterministic regardless of the os.walk order the scan produced.
    for entry in sorted(iter_dirty_entries(cache_dir), key=lambda e: e.path):
        if entry.is_orphaned:
            record = _clear_orphan(cache_dir, entry)
            if record is None:
                continue
            _log("orphaned_dirty_entry_reconciled", **record)
        elif entry.is_inconsistent:
            status, remote = probe.lookup(entry.path) if probe is not None else (ERROR, None)
            # Repair only when the upload it enables cannot destroy anything:
            # either the cloud object is still the one this entry was derived
            # from, or there is no cloud object to overwrite at all.
            if status == FOUND and fingerprint_matches(entry.fingerprint, remote):
                reason = None
            elif status == ABSENT and not entry.fingerprint:
                reason = None
            elif status == FOUND:
                reason = "fingerprint_mismatch"   # a second writer moved it
            elif status == ABSENT:
                reason = "remote_deleted"         # it existed once; now it doesn't
            else:
                reason = "remote_unverifiable"    # we could not look it up
            if reason is None:
                record = repair_metadata(cache_dir, entry)
                _log("desynced_dirty_entry_repaired", **record)
            else:
                record = quarantine_entry(
                    cache_dir, entry, reason,
                    recorded_fingerprint=entry.fingerprint,
                    remote_size=(remote or {}).get("Size"),
                    remote_modtime=(remote or {}).get("ModTime"),
                )
                _log("desynced_dirty_entry_quarantined", **record)
        else:
            # Dirty with consistent data → a resumable upload; leave it.
            continue
        reconciled.append(record)
    return reconciled


def main(argv: list[str]) -> int:
    cache_dir = argv[1] if len(argv) > 1 else os.environ.get("WORKSPACE_CACHE_DIR", "/cache")
    # The serve target lets the reconcile stat the cloud object behind an
    # inconsistent entry. Without it, inconsistent entries are quarantined rather
    # than repaired — safe, but it needs an operator to recover the content.
    target = argv[2] if len(argv) > 2 else os.environ.get("WORKSPACE_SERVE_TARGET", "")
    probe = RcloneRemoteProbe(target) if target else None
    if probe is None:
        _log("cache_reconcile_no_remote_probe", cache_dir=cache_dir,
             detail="no serve target given; inconsistent entries will be quarantined, not repaired")
    try:
        reconciled = reconcile_cache(cache_dir, probe=probe)
    except Exception as exc:  # noqa: BLE001 — never block serving on reconcile
        _log("cache_reconcile_failed", cache_dir=cache_dir, error=str(exc))
        return 0
    actions: dict[str, int] = {}
    for record in reconciled:
        actions[record["action"]] = actions.get(record["action"], 0) + 1
    _log("cache_reconcile_complete", cache_dir=cache_dir, reconciled=len(reconciled), actions=actions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
