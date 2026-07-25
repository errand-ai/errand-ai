#!/usr/bin/env python3
"""Reconcile orphaned dirty entries in the rclone VFS cache before serving.

Run once by the gateway entrypoint, *before* `rclone serve` starts, over the
persistent `--vfs-cache-mode full` cache directory.

Background (the incident this closes)
-------------------------------------
A completed write goes: task `close()` → rclone marks the VFS item dirty and
writes its data into the cache → write-back uploads it. In production a dirty
item was observed with **no data to upload**::

    vfsMeta/<remote>/.../BlogsToProcess.md : {"Dirty": true, "Size": 0, "Rs": null}
    vfs/<remote>/.../BlogsToProcess.md      : (missing)
    vfs/stats                               : uploadsQueued: 0, erroredFiles: 0

rclone recorded a dirty change, lost the data backing it, and never queued an
upload — a terminal "dirty but idle" state. Such an entry is *not* a resumable
upload: there is nothing to send. Left in place it can block change-polling or
cause an empty file to be uploaded over the good cloud copy.

What this does
--------------
Scan `<cache_dir>/vfsMeta/**` for entries whose metadata marks them dirty
(`"Dirty": true`) but which have no data to upload — the sibling data file under
`<cache_dir>/vfs/**` is missing or zero-length. For each such orphan, remove the
stale meta (and any zero-length data file) so that on the first serve + poll
rclone re-fetches the current cloud object instead of acting on a phantom write.
A genuinely resumable pending upload (dirty meta *with* a non-empty data file) is
left untouched so `rclone serve` resumes it on start.

Every reconciled entry is logged as one structured JSON line. The scan is
best-effort: it never raises out of `main()` (a reconcile failure must not stop
the gateway from serving), and it only ever removes files it has positively
identified as orphaned dirty entries.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Iterator, NamedTuple

# rclone lays the VFS cache out as two parallel trees under the cache dir:
#   <cache_dir>/vfs/<remote>/<path>      — the cached file data
#   <cache_dir>/vfsMeta/<remote>/<path>  — per-item JSON metadata (Dirty, Size, …)
_DATA_SUBDIR = "vfs"
_META_SUBDIR = "vfsMeta"


class DirtyEntry(NamedTuple):
    """A cache entry marked dirty (not-yet-uploaded) in its VFS metadata."""

    path: str          # cache-relative path, e.g. "<remote>/dir/file"
    meta: dict         # parsed item metadata (Dirty, Size, Fingerprint, …)
    data_path: str     # absolute path to the sibling data file (may not exist)
    has_data: bool     # True if a non-empty data file backs the entry

    @property
    def fingerprint(self):
        return self.meta.get("Fingerprint")

    @property
    def is_orphaned(self) -> bool:
        """Dirty but nothing to upload — the terminal, silent data-loss state.

        A resumable pending upload has a non-empty data file; an orphan has no
        data file at all, or a zero-length one (the incident's ``Size: 0`` case).
        """
        return not self.has_data


def _log(event: str, **fields) -> None:
    """Emit one structured JSON log line (matches the refresher's format)."""
    print(json.dumps({"component": "workspace-gateway", "event": event, **fields}), file=sys.stderr)


def _is_dirty(meta: dict) -> bool:
    """True if the item metadata marks the entry dirty (not-yet-uploaded)."""
    return bool(meta.get("Dirty"))


def _has_upload_data(data_path: str) -> bool:
    """True if there is real data to upload for this entry."""
    try:
        return os.path.getsize(data_path) > 0
    except OSError:
        return False


def iter_dirty_entries(cache_dir: str) -> Iterator[DirtyEntry]:
    """Yield every dirty entry in the VFS cache under ``cache_dir``.

    Shared by the startup reconcile (which removes orphaned ones) and the
    refresher's write-back health scan (which tracks dirty age and fingerprints).
    Non-dirty entries are ordinary read cache and are skipped. Meta files that
    are unreadable or not JSON are skipped rather than guessed at.
    """
    meta_root = os.path.join(cache_dir, _META_SUBDIR)
    data_root = os.path.join(cache_dir, _DATA_SUBDIR)
    if not os.path.isdir(meta_root):
        return
    for dirpath, _dirs, files in os.walk(meta_root):
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
            yield DirtyEntry(
                path=rel,
                meta=meta,
                data_path=data_path,
                has_data=_has_upload_data(data_path),
            )


def reconcile_cache(cache_dir: str) -> list[dict]:
    """Remove orphaned dirty entries from the VFS cache under ``cache_dir``.

    Returns a list of reconciliation records, one per orphaned entry acted on::

        {"path": "<remote>/…/file", "action": "cleared_orphaned_dirty_meta",
         "removed": ["vfsMeta/…", "vfs/…"]}

    A dirty entry that still has data to upload is preserved (so ``rclone serve``
    resumes it). Non-dirty entries are ordinary read cache and are left alone.
    """
    reconciled: list[dict] = []
    for entry in iter_dirty_entries(cache_dir):
        if not entry.is_orphaned:
            # Dirty with data present → a resumable upload; leave it.
            continue

        meta_path = os.path.join(cache_dir, _META_SUBDIR, entry.path)
        removed: list[str] = []
        # Remove a zero-length data file first (if present), then the meta, so a
        # crash mid-reconcile never leaves data without its meta.
        for target, label in ((entry.data_path, _DATA_SUBDIR), (meta_path, _META_SUBDIR)):
            try:
                os.remove(target)
                removed.append(f"{label}/{entry.path}")
            except OSError:
                pass
        record = {
            "path": entry.path,
            "action": "cleared_orphaned_dirty_meta",
            "meta_size": entry.meta.get("Size"),
            "removed": removed,
        }
        reconciled.append(record)
        _log("orphaned_dirty_entry_reconciled", **record)
    return reconciled


def main(argv: list[str]) -> int:
    cache_dir = argv[1] if len(argv) > 1 else os.environ.get("WORKSPACE_CACHE_DIR", "/cache")
    try:
        reconciled = reconcile_cache(cache_dir)
    except Exception as exc:  # noqa: BLE001 — never block serving on reconcile
        _log("cache_reconcile_failed", cache_dir=cache_dir, error=str(exc))
        return 0
    _log("cache_reconcile_complete", cache_dir=cache_dir, reconciled=len(reconciled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
