"""Tests for the startup VFS-cache orphaned-dirty-entry reconcile.

Covers the fault-injection scenario (tasks.md 6.2 / spec "Orphaned dirty entry
recovered on restart"): a dirty entry with no data to upload is reconciled away
(so it can't block change-polling or upload an empty file), while a genuinely
resumable pending upload is preserved.
"""

import json
import os

import cache_reconcile as cr


def _write_meta(cache_dir, rel, *, dirty, size=0, fingerprint="fp"):
    p = os.path.join(cache_dir, "vfsMeta", rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump({"Dirty": dirty, "Size": size, "Rs": None, "Fingerprint": fingerprint}, f)
    return p


def _write_data(cache_dir, rel, content):
    p = os.path.join(cache_dir, "vfs", rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(content)
    return p


def _meta_path(cache_dir, rel):
    return os.path.join(cache_dir, "vfsMeta", rel)


def _data_path(cache_dir, rel):
    return os.path.join(cache_dir, "vfs", rel)


def test_orphaned_dirty_entry_is_removed(tmp_path):
    cache = str(tmp_path)
    _write_meta(cache, "gd/orphan.md", dirty=True, size=0)  # dirty, no data file

    reconciled = cr.reconcile_cache(cache)

    assert [r["path"] for r in reconciled] == ["gd/orphan.md"]
    assert reconciled[0]["action"] == "cleared_orphaned_dirty_meta"
    assert not os.path.exists(_meta_path(cache, "gd/orphan.md"))


def test_zero_length_data_file_orphan_is_removed(tmp_path):
    # The incident's exact shape: Size:0 meta AND a zero-length data file.
    cache = str(tmp_path)
    _write_meta(cache, "gd/empty.md", dirty=True, size=0)
    _write_data(cache, "gd/empty.md", "")  # empty data file — nothing to upload

    reconciled = cr.reconcile_cache(cache)

    assert [r["path"] for r in reconciled] == ["gd/empty.md"]
    # Both the stale meta and the empty data file are cleared.
    assert not os.path.exists(_meta_path(cache, "gd/empty.md"))
    assert not os.path.exists(_data_path(cache, "gd/empty.md"))


def test_resumable_pending_upload_is_preserved(tmp_path):
    # Dirty WITH non-empty data == a resumable upload; rclone must resume it.
    cache = str(tmp_path)
    _write_meta(cache, "gd/resumable.md", dirty=True, size=5)
    _write_data(cache, "gd/resumable.md", "hello")

    reconciled = cr.reconcile_cache(cache)

    assert reconciled == []
    assert os.path.exists(_meta_path(cache, "gd/resumable.md"))
    assert os.path.exists(_data_path(cache, "gd/resumable.md"))


def test_clean_entry_is_left_alone(tmp_path):
    cache = str(tmp_path)
    _write_meta(cache, "gd/clean.md", dirty=False, size=5)
    _write_data(cache, "gd/clean.md", "hello")

    reconciled = cr.reconcile_cache(cache)

    assert reconciled == []
    assert os.path.exists(_meta_path(cache, "gd/clean.md"))


def test_missing_cache_dir_is_noop(tmp_path):
    assert cr.reconcile_cache(str(tmp_path / "does-not-exist")) == []


def test_unreadable_meta_is_skipped_not_deleted(tmp_path):
    # A meta file that isn't valid JSON must be left for rclone, never guessed at.
    cache = str(tmp_path)
    p = os.path.join(cache, "vfsMeta", "gd/garbage.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write("not json {{{")

    reconciled = cr.reconcile_cache(cache)

    assert reconciled == []
    assert os.path.exists(p)


def test_iter_dirty_entries_reports_orphan_and_resumable(tmp_path):
    cache = str(tmp_path)
    _write_meta(cache, "gd/orphan.md", dirty=True, size=0)
    _write_meta(cache, "gd/resumable.md", dirty=True, size=5)
    _write_data(cache, "gd/resumable.md", "hello")
    _write_meta(cache, "gd/clean.md", dirty=False, size=5)

    by_path = {e.path: e for e in cr.iter_dirty_entries(cache)}

    assert set(by_path) == {"gd/orphan.md", "gd/resumable.md"}  # clean excluded
    assert by_path["gd/orphan.md"].is_orphaned is True
    assert by_path["gd/resumable.md"].is_orphaned is False


def test_main_never_raises_and_returns_zero(tmp_path, capsys):
    # Best-effort contract: main() must return 0 even on a good run, so a
    # reconcile step can never block the gateway from serving.
    _write_meta(str(tmp_path), "gd/orphan.md", dirty=True, size=0)
    rc = cr.main(["cache_reconcile.py", str(tmp_path)])
    assert rc == 0
    events = [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert "orphaned_dirty_entry_reconciled" in events
    assert "cache_reconcile_complete" in events
