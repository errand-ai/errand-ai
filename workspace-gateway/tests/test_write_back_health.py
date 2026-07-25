"""Tests for write-back health / stuck-upload detection in the refresher.

Covers tasks.md 6.3 and the "Write-back health and stuck-upload detection"
requirement: a dirty entry stuck past the grace period, or a non-zero
erroredFiles count, degrades write-back health and logs a structured error; and
the concurrent-writer fingerprint-change warning (spec 5.2).
"""

import json

import pytest

import cache_reconcile as cr
from refresher import WriteBackMonitor, _parse_duration


class _Cfg:
    """Minimal stand-in for refresher.Config (only what the monitor reads)."""

    def __init__(self, grace=30.0):
        self.stuck_grace_seconds = grace


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _entry(path, *, has_data, fingerprint="fp", size=0):
    return cr.DirtyEntry(
        path=path,
        meta={"Dirty": True, "Size": size, "Fingerprint": fingerprint},
        data_path=f"/cache/vfs/{path}",
        has_data=has_data,
    )


def _stats(queued=0, in_progress=0, errored=0):
    return {"uploads_queued": queued, "uploads_in_progress": in_progress, "errored_files": errored}


def test_fresh_dirty_entry_is_healthy():
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    health = mon.evaluate(_stats(), [_entry("gd/a.md", has_data=False)])
    assert health["write_back_state"] == "ok"
    assert health["write_back"]["dirty_entries"] == 1
    assert health["write_back"]["stuck_entries"] == []


def test_orphan_dirty_past_grace_degrades(caplog):
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    entries = [_entry("gd/orphan.md", has_data=False)]
    assert mon.evaluate(_stats(), entries)["write_back_state"] == "ok"  # age 0

    clock.t = 31.0
    with caplog.at_level("INFO"):
        health = mon.evaluate(_stats(), entries)

    assert health["write_back_state"] == "degraded"
    assert health["write_back"]["stuck_entries"] == ["gd/orphan.md"]
    err = health["write_back_errors"][0]
    assert err["path"] == "gd/orphan.md"
    assert err["reason"] == "orphaned_dirty_entry"
    # Structured, alertable log naming the path.
    logged = [json.loads(r.message) for r in caplog.records if r.message.startswith("{")]
    assert any(e.get("event") == "write_back_degraded" and e.get("path") == "gd/orphan.md" for e in logged)


def test_dirty_with_data_but_idle_queue_past_grace_degrades():
    # Data present (would be resumable) but nothing queued/uploading for it and
    # it has aged out — the queue is idle, so it is stuck.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    entries = [_entry("gd/b.md", has_data=True)]
    mon.evaluate(_stats(queued=0, in_progress=0), entries)
    clock.t = 31.0
    health = mon.evaluate(_stats(queued=0, in_progress=0), entries)
    assert health["write_back_state"] == "degraded"
    assert health["write_back_errors"][0]["reason"] == "dirty_entry_not_progressing"


def test_dirty_with_data_and_active_queue_stays_healthy():
    # Same aged entry, but the upload queue is active → progressing, not stuck.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    entries = [_entry("gd/b.md", has_data=True)]
    mon.evaluate(_stats(queued=1), entries)
    clock.t = 31.0
    health = mon.evaluate(_stats(queued=1), entries)
    assert health["write_back_state"] == "ok"
    assert health["write_back"]["stuck_entries"] == []


def test_unknown_queue_state_does_not_falsely_degrade_dirty_with_data():
    # rc outage: read_vfs_stats returns None counters. A dirty-with-data entry
    # past grace must NOT be flagged stuck — we don't know the queue is idle.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    unknown = {"uploads_queued": None, "uploads_in_progress": None, "errored_files": None}
    entries = [_entry("gd/b.md", has_data=True)]
    mon.evaluate(unknown, entries)
    clock.t = 31.0
    health = mon.evaluate(unknown, entries)
    assert health["write_back_state"] == "ok"
    assert health["write_back"]["stuck_entries"] == []


def test_unknown_queue_state_still_flags_orphan():
    # An orphan can never upload, so it is stuck independent of queue state —
    # even when rc stats are unavailable.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    unknown = {"uploads_queued": None, "uploads_in_progress": None, "errored_files": None}
    entries = [_entry("gd/orphan.md", has_data=False)]
    mon.evaluate(unknown, entries)
    clock.t = 31.0
    health = mon.evaluate(unknown, entries)
    assert health["write_back_state"] == "degraded"
    assert health["write_back_errors"][0]["reason"] == "orphaned_dirty_entry"


def test_errored_files_is_degraded_regardless_of_age():
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=_Clock())
    health = mon.evaluate(_stats(errored=2), [])
    assert health["write_back_state"] == "degraded"
    assert health["write_back_errors"][0]["reason"] == "errored_uploads"
    assert health["write_back_errors"][0]["errored_files"] == 2


def test_entry_cleared_after_upload_forgets_state():
    # Once an entry uploads (no longer dirty), a later re-dirty starts a fresh
    # age clock — stale per-path state must not linger and instantly re-degrade.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    entries = [_entry("gd/c.md", has_data=False)]
    mon.evaluate(_stats(), entries)
    clock.t = 100.0
    mon.evaluate(_stats(), [])          # entry uploaded/gone → state forgotten
    health = mon.evaluate(_stats(), entries)   # re-dirtied now
    assert health["write_back_state"] == "ok"  # fresh clock, not instantly stuck


def test_concurrent_writer_fingerprint_change_warns(caplog):
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    mon.evaluate(_stats(), [_entry("gd/shared.md", has_data=False, fingerprint="v1")])
    with caplog.at_level("INFO"):
        mon.evaluate(_stats(), [_entry("gd/shared.md", has_data=False, fingerprint="v2")])
    logged = [json.loads(r.message) for r in caplog.records if r.message.startswith("{")]
    warn = [e for e in logged if e.get("event") == "concurrent_writer_detected"]
    assert warn and warn[0]["path"] == "gd/shared.md"
    assert warn[0]["remote_fingerprint"] == "v2"


@pytest.mark.parametrize(
    "text,expected",
    [("1s", 1.0), ("500ms", 0.5), ("2m", 120.0), ("1h", 3600.0), ("5", 5.0), ("", 1.0), ("garbage", 1.0)],
)
def test_parse_duration(text, expected):
    assert _parse_duration(text, 1.0) == expected
