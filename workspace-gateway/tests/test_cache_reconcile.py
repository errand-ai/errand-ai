"""Tests for the startup VFS-cache reconcile.

Covers both production fault signatures:

  * **orphaned** (2026-07-25, spec "Orphaned dirty entry recovered on restart"):
    a dirty entry with no data to upload is reconciled away, so it can't block
    change-polling or upload an empty file, while a genuinely resumable pending
    upload is preserved;
  * **desynced** (2026-07-26, spec "Metadata/data desync is detected and
    repaired"): a dirty entry whose metadata reports `Size: 0` / `Rs: null` while
    a non-empty data file is present is repaired (fingerprint still matching) or
    quarantined (remote moved / unverifiable) — and its data is never deleted.
"""

import json
import os

import pytest

import cache_reconcile as cr

# The exact production signature from the 2026-07-26 incident: the cached data
# file held 56254 bytes of real user work while the metadata claimed the item was
# empty. Uploading from this state published a same-length corrupted object.
_PROD_DATA_SIZE = 56254
_PROD_FINGERPRINT = "63805,2026-07-26T19:28:15Z,2bbf85b7c0ffee00d15ea5ed0badf00d"
_PROD_REMOTE = {"Size": 63805, "ModTime": "2026-07-26T19:28:15Z",
                "Hashes": {"md5": "2bbf85b7c0ffee00d15ea5ed0badf00d"}}


class _Probe:
    """Stand-in for RcloneRemoteProbe: returns a canned lookup, records calls."""

    def __init__(self, item, status=None):
        self.item = item
        self.status = status or (cr.FOUND if item else cr.ERROR)
        self.calls = []

    def lookup(self, cache_path):
        self.calls.append(cache_path)
        return self.status, self.item


def _write_meta(cache_dir, rel, *, dirty, size=0, fingerprint="fp", rs=None):
    p = os.path.join(cache_dir, "vfsMeta", rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump({"Dirty": dirty, "Size": size, "Rs": rs, "Fingerprint": fingerprint}, f)
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


def test_zero_length_data_file_is_preserved_as_empty_write(tmp_path):
    # A dirty entry whose data file EXISTS but is zero-length is a legitimate
    # empty-file write (a task truncating/creating a file to empty), NOT an
    # orphan — it must be preserved so rclone uploads the empty file. Only a
    # *missing* data file is an orphan.
    cache = str(tmp_path)
    _write_meta(cache, "gd/empty.md", dirty=True, size=0)
    _write_data(cache, "gd/empty.md", "")  # empty data file EXISTS

    reconciled = cr.reconcile_cache(cache)

    assert reconciled == []
    assert os.path.exists(_meta_path(cache, "gd/empty.md"))
    assert os.path.exists(_data_path(cache, "gd/empty.md"))


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


def test_reconciled_entries_are_returned_in_sorted_order(tmp_path):
    # Order must be deterministic (sorted by path), not os.walk order.
    cache = str(tmp_path)
    for rel in ("gd/z.md", "gd/a.md", "gd/m.md"):
        _write_meta(cache, rel, dirty=True, size=0)

    reconciled = cr.reconcile_cache(cache)

    assert [r["path"] for r in reconciled] == ["gd/a.md", "gd/m.md", "gd/z.md"]


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


def test_meta_removal_failure_is_not_reported_as_reconciled(tmp_path, monkeypatch, capsys):
    # If the meta file can't be removed (permissions/busy), the orphan is NOT
    # cleared — it must be surfaced as a remove failure, not a reconciled entry.
    cache = str(tmp_path)
    _write_meta(cache, "gd/stuck.md", dirty=True, size=0)

    real_remove = os.remove

    def flaky_remove(path):
        if path.endswith(os.path.join("vfsMeta", "gd/stuck.md")) or path.endswith("vfsMeta/gd/stuck.md"):
            raise PermissionError("read-only cache")
        return real_remove(path)

    monkeypatch.setattr(os, "remove", flaky_remove)
    reconciled = cr.reconcile_cache(cache)

    assert reconciled == []  # not counted as reconciled
    events = [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert "orphaned_dirty_entry_remove_failed" in events
    assert "orphaned_dirty_entry_reconciled" not in events


def test_unstattable_data_file_is_treated_as_having_data(tmp_path, monkeypatch):
    # A data file that exists but can't be stat'd (permissions / transient I/O)
    # must NOT be classified as orphaned — deleting it would discard a real
    # pending upload. Only a genuinely-absent file counts as "no data".
    cache = str(tmp_path)
    _write_meta(cache, "gd/locked.md", dirty=True, size=5)
    _write_data(cache, "gd/locked.md", "hello")

    real_stat = os.stat

    def flaky_stat(path, *args, **kwargs):
        if isinstance(path, str) and path.endswith("locked.md"):
            raise PermissionError("cannot stat")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", flaky_stat)
    reconciled = cr.reconcile_cache(cache)
    monkeypatch.undo()  # restore os.stat before the filesystem assertions below

    assert reconciled == []  # preserved, not deleted
    assert os.path.exists(_meta_path(cache, "gd/locked.md"))
    assert os.path.exists(_data_path(cache, "gd/locked.md"))


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


def _quarantine_dir(cache_dir):
    return os.path.join(cache_dir, "quarantine")


def _write_prod_signature(cache, rel="gd/workflow/BlogsToProcess.md"):
    """Lay down the exact 2026-07-26 fault: Size 0 / Rs null, data file present."""
    _write_meta(cache, rel, dirty=True, size=0, rs=None, fingerprint=_PROD_FINGERPRINT)
    _write_data(cache, rel, "x" * _PROD_DATA_SIZE)
    return rel


def test_desynced_entry_is_repaired_when_fingerprint_matches(tmp_path):
    # The remote is still the object this entry was derived from, so the cached
    # content is a safe successor: repair the metadata to match the data file and
    # leave the entry dirty so the COMPLETE content uploads.
    cache = str(tmp_path)
    rel = _write_prod_signature(cache)
    probe = _Probe(_PROD_REMOTE)

    reconciled = cr.reconcile_cache(cache, probe=probe)

    assert [r["action"] for r in reconciled] == ["repaired_desynced_meta"]
    assert reconciled[0]["data_size"] == _PROD_DATA_SIZE
    meta = json.load(open(_meta_path(cache, rel)))
    assert meta["Size"] == _PROD_DATA_SIZE
    assert meta["Rs"] == [{"Pos": 0, "Size": _PROD_DATA_SIZE}]
    assert meta["Dirty"] is True          # still dirty → rclone uploads it
    assert meta["Fingerprint"] == _PROD_FINGERPRINT  # untouched
    # The data file — the only copy of the user's work — is unchanged.
    assert os.path.getsize(_data_path(cache, rel)) == _PROD_DATA_SIZE


def test_desynced_entry_is_quarantined_when_remote_moved(tmp_path):
    # The cloud object changed underneath the dirty entry (a second writer).
    # Uploading the local copy would overwrite the newer remote, so quarantine.
    cache = str(tmp_path)
    rel = _write_prod_signature(cache)
    moved = {"Size": 99999, "ModTime": "2026-07-27T08:00:00Z", "Hashes": {"md5": "deadbeef"}}

    reconciled = cr.reconcile_cache(cache, probe=_Probe(moved))

    assert [r["action"] for r in reconciled] == ["quarantined"]
    assert reconciled[0]["reason"] == "fingerprint_mismatch"
    assert reconciled[0]["remote_size"] == 99999
    # Moved out of the live cache so rclone can't publish it...
    assert not os.path.exists(_meta_path(cache, rel))
    assert not os.path.exists(_data_path(cache, rel))
    # ...but retained in full for manual recovery.
    quarantined = os.path.join(_quarantine_dir(cache), "vfs", rel)
    assert os.path.getsize(quarantined) == _PROD_DATA_SIZE
    assert os.path.exists(os.path.join(_quarantine_dir(cache), "vfsMeta", rel))


def test_desynced_entry_is_quarantined_when_remote_unverifiable(tmp_path):
    # Cannot read the remote → cannot justify publishing over it. A
    # stalled-but-reported write is recoverable; a torn published write may not be.
    cache = str(tmp_path)
    rel = _write_prod_signature(cache)

    reconciled = cr.reconcile_cache(cache, probe=_Probe(None))

    assert reconciled[0]["reason"] == "remote_unverifiable"
    assert os.path.getsize(os.path.join(_quarantine_dir(cache), "vfs", rel)) == _PROD_DATA_SIZE


def test_desynced_entry_without_a_probe_is_quarantined_not_uploaded(tmp_path):
    # No probe configured at all (no serve target): still never publish blind.
    cache = str(tmp_path)
    rel = _write_prod_signature(cache)

    reconciled = cr.reconcile_cache(cache)

    assert reconciled[0]["action"] == "quarantined"
    assert os.path.getsize(os.path.join(_quarantine_dir(cache), "vfs", rel)) == _PROD_DATA_SIZE


def test_quarantine_records_a_manifest_line(tmp_path):
    # The runbook recovery procedure reads this manifest.
    cache = str(tmp_path)
    rel = _write_prod_signature(cache)
    cr.reconcile_cache(cache, probe=_Probe(None))

    lines = open(os.path.join(_quarantine_dir(cache), "manifest.jsonl")).read().splitlines()
    record = json.loads(lines[0])
    assert record["path"] == rel
    assert record["reason"] == "remote_unverifiable"
    assert record["data_size"] == _PROD_DATA_SIZE
    assert record["quarantined_at"]


def test_repeated_quarantine_of_the_same_path_does_not_overwrite(tmp_path):
    # A second incident on the same path must not clobber the first rescue copy.
    cache = str(tmp_path)
    rel = _write_prod_signature(cache)
    cr.reconcile_cache(cache, probe=_Probe(None))
    _write_meta(cache, rel, dirty=True, size=0, rs=None, fingerprint=_PROD_FINGERPRINT)
    _write_data(cache, rel, "second incident")
    cr.reconcile_cache(cache, probe=_Probe(None))

    first = os.path.join(_quarantine_dir(cache), "vfs", rel)
    assert os.path.getsize(first) == _PROD_DATA_SIZE      # original preserved
    assert open(first + ".1").read() == "second incident"


def test_orphaned_entry_still_reconciled_when_a_probe_is_present(tmp_path):
    # Regression: the desync path must not change how absent-data orphans are
    # handled — they are cleared, without consulting the remote at all.
    cache = str(tmp_path)
    _write_meta(cache, "gd/orphan.md", dirty=True, size=0)
    probe = _Probe(_PROD_REMOTE)

    reconciled = cr.reconcile_cache(cache, probe=probe)

    assert [r["action"] for r in reconciled] == ["cleared_orphaned_dirty_meta"]
    assert not os.path.exists(_meta_path(cache, "gd/orphan.md"))
    assert probe.calls == []  # no remote stat needed to clear an orphan


def test_dirty_entry_with_read_ranges_is_left_alone(tmp_path):
    # Rs present == a genuinely resumable partial item, not the desync fault.
    cache = str(tmp_path)
    _write_meta(cache, "gd/partial.md", dirty=True, size=0, rs=[{"Pos": 0, "Size": 10}])
    _write_data(cache, "gd/partial.md", "0123456789")

    assert cr.reconcile_cache(cache, probe=_Probe(_PROD_REMOTE)) == []
    assert os.path.exists(_meta_path(cache, "gd/partial.md"))


def test_unstattable_data_file_is_not_repaired(tmp_path, monkeypatch):
    # Unknown data length → we cannot write a truthful Size, so don't guess.
    cache = str(tmp_path)
    _write_prod_signature(cache, "gd/locked.md")
    real_stat = os.stat

    def flaky_stat(path, *args, **kwargs):
        if isinstance(path, str) and "vfs/gd/locked.md" in path.replace(os.sep, "/"):
            raise PermissionError("cannot stat")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", flaky_stat)
    reconciled = cr.reconcile_cache(cache, probe=_Probe(_PROD_REMOTE))
    monkeypatch.undo()

    assert reconciled == []
    assert os.path.getsize(_data_path(cache, "gd/locked.md")) == _PROD_DATA_SIZE


def test_unreadable_cache_raises_rather_than_scanning_zero_entries(tmp_path):
    # THE bug that made the 2026-07-26 stall invisible: os.walk's default is to
    # skip an unreadable directory, so the scan returned NO entries and the
    # monitor reported "0 dirty, healthy" while writes sat unuploaded. A scan
    # that cannot see the cache must fail loudly instead.
    cache = str(tmp_path)
    _write_meta(cache, "gd/a.md", dirty=True, size=0)
    meta_root = os.path.join(cache, "vfsMeta")
    os.chmod(meta_root, 0o000)
    try:
        with pytest.raises(OSError):
            list(cr.iter_dirty_entries(cache))
    finally:
        os.chmod(meta_root, 0o755)


def test_unreadable_subdirectory_also_raises(tmp_path):
    # Blindness below the root is just as silent as blindness at the root.
    cache = str(tmp_path)
    _write_meta(cache, "gd/sub/a.md", dirty=True, size=0)
    subdir = os.path.join(cache, "vfsMeta", "gd", "sub")
    os.chmod(subdir, 0o000)
    try:
        with pytest.raises(OSError):
            list(cr.iter_dirty_entries(cache))
    finally:
        os.chmod(subdir, 0o755)


@pytest.mark.parametrize(
    "fingerprint,remote,expected",
    [
        (_PROD_FINGERPRINT, _PROD_REMOTE, True),
        (_PROD_FINGERPRINT, None, False),                                   # unreadable remote
        (_PROD_FINGERPRINT, {**_PROD_REMOTE, "Size": 1}, False),            # size moved
        (_PROD_FINGERPRINT, {**_PROD_REMOTE, "Hashes": {"md5": "ff"}}, False),  # content changed
        # No hash on the remote → fall back to size + modtime.
        ("63805,2026-07-26T19:28:15Z", {"Size": 63805, "ModTime": "2026-07-26T19:28:15Z"}, True),
        ("63805,2026-07-26T19:28:15Z", {"Size": 63805, "ModTime": "2026-07-26T20:00:00Z"}, False),
        (None, _PROD_REMOTE, False),                                        # nothing recorded
        ("", _PROD_REMOTE, False),
        ("garbage", _PROD_REMOTE, False),
    ],
)
def test_fingerprint_matches(fingerprint, remote, expected):
    assert cr.fingerprint_matches(fingerprint, remote) is expected


def _probe_with_index(index, target="gdrive:Errand"):
    probe = cr.RcloneRemoteProbe(target)
    probe._index = index
    return probe


def test_probe_resolves_paths_by_longest_matching_suffix():
    # A cache path is NOT "<remote>/<path>": rclone keys the cache by the fs's
    # identity AND its full root, so serving `gdrive:Errand` caches
    # `notes/todo.md` under `gdrive{…}/Errand/notes/todo.md`, and an alias remote
    # expands further (`loc:Errand` → `local/tmp/data/Errand/…`, verified against
    # rclone 1.68). The prefix depth is not derivable from the target string, so
    # paths are resolved against a real listing instead of being guessed.
    index = {"notes/todo.md": {"Size": 7}, "top.md": {"Size": 3}}

    probe = _probe_with_index(index)
    assert probe.lookup("gdrive{a1b2}/Errand/notes/todo.md") == (cr.FOUND, {"Size": 7})
    assert probe.lookup("gdrive{a1b2}/top.md") == (cr.FOUND, {"Size": 3})
    # Deeply nested fs-root prefixes (alias/local backends) resolve the same way.
    assert probe.lookup("local/tmp/data/Errand/notes/todo.md") == (cr.FOUND, {"Size": 7})


def test_probe_reports_absent_distinctly_from_error():
    # "Demonstrably not there" and "couldn't look" lead to different decisions:
    # the first cannot be overwritten by an upload, the second might be anything.
    probe = _probe_with_index({"notes/todo.md": {"Size": 7}})
    assert probe.lookup("gdrive{a1b2}/Errand/gone.md") == (cr.ABSENT, None)

    failed = cr.RcloneRemoteProbe("gdrive:Errand")
    failed._index_failed = True
    assert failed.lookup("gdrive{a1b2}/Errand/anything.md") == (cr.ERROR, None)


def test_probe_lists_the_remote_only_once(monkeypatch):
    # The listing is lazy and cached: it must not be re-run per entry, and must
    # not run at all when nothing needs verifying.
    calls = []

    class _Proc:
        returncode = 0
        stdout = json.dumps([{"Path": "notes/todo.md", "Size": 7}])
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _Proc()

    monkeypatch.setattr(cr.subprocess, "run", fake_run)
    probe = cr.RcloneRemoteProbe("gdrive:Errand")
    probe.lookup("gdrive{a1b2}/Errand/notes/todo.md")
    probe.lookup("gdrive{a1b2}/Errand/other.md")

    assert len(calls) == 1
    assert calls[0][:4] == ["rclone", "lsjson", "-R", "--files-only"]
    assert calls[0][-1] == "gdrive:Errand"


def test_probe_does_not_list_when_no_entry_needs_verifying(tmp_path, monkeypatch):
    # An orphan-only reconcile must not pay for a recursive remote listing.
    calls = []
    monkeypatch.setattr(cr.subprocess, "run", lambda *a, **k: calls.append(a) or _fail())
    cache = str(tmp_path)
    _write_meta(cache, "gd/orphan.md", dirty=True, size=0)

    cr.reconcile_cache(cache, probe=cr.RcloneRemoteProbe("gdrive:Errand"))

    assert calls == []


def _fail():
    raise AssertionError("rclone should not have been invoked")


def test_desynced_entry_absent_remotely_with_no_fingerprint_is_repaired(tmp_path):
    # A brand-new file that never reached the cloud: there is nothing to
    # overwrite, so quarantining it would strand real work for no safety gain.
    cache = str(tmp_path)
    rel = "gd/Errand/brand-new.md"
    _write_meta(cache, rel, dirty=True, size=0, rs=None, fingerprint=None)
    _write_data(cache, rel, "fresh work")

    reconciled = cr.reconcile_cache(cache, probe=_Probe(None, status=cr.ABSENT))

    assert reconciled[0]["action"] == "repaired_desynced_meta"
    assert json.load(open(_meta_path(cache, rel)))["Size"] == len("fresh work")


def test_desynced_entry_absent_remotely_with_a_fingerprint_is_quarantined(tmp_path):
    # It existed when this entry was cached and does not now — something else
    # deleted or moved it, so publishing over that decision needs a human.
    cache = str(tmp_path)
    rel = _write_prod_signature(cache)

    reconciled = cr.reconcile_cache(cache, probe=_Probe(None, status=cr.ABSENT))

    assert reconciled[0]["reason"] == "remote_deleted"
    assert os.path.getsize(os.path.join(_quarantine_dir(cache), "vfs", rel)) == _PROD_DATA_SIZE


def test_main_never_raises_and_returns_zero(tmp_path, capsys):
    # Best-effort contract: main() must return 0 even on a good run, so a
    # reconcile step can never block the gateway from serving.
    _write_meta(str(tmp_path), "gd/orphan.md", dirty=True, size=0)
    rc = cr.main(["cache_reconcile.py", str(tmp_path)])
    assert rc == 0
    events = [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert "orphaned_dirty_entry_reconciled" in events
    assert "cache_reconcile_complete" in events
