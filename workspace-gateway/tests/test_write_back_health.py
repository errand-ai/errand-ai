"""Tests for write-back health / stuck-upload detection in the refresher.

Covers tasks.md 6.3 and the "Write-back health and stuck-upload detection"
requirement: a dirty entry stuck past the grace period, or a non-zero
erroredFiles count, degrades write-back health and logs a structured error; and
the concurrent-writer fingerprint-change warning (spec 5.2).
"""

import json
import os

import pytest

import cache_reconcile as cr
from refresher import WriteBackMonitor, _parse_duration


class _Cfg:
    """Minimal stand-in for refresher.Config (only what the monitor reads)."""

    def __init__(self, grace=30.0, max_dirty_age=900.0, force_flush=False):
        self.stuck_grace_seconds = grace
        self.max_dirty_age_seconds = max_dirty_age
        self.force_flush_pinned = force_flush


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _entry(path, *, has_data, fingerprint="fp", size=0, data_size=None):
    if data_size is None and has_data:
        data_size = size or 1
    return cr.DirtyEntry(
        path=path,
        meta={"Dirty": True, "Size": size, "Fingerprint": fingerprint},
        data_path=f"/cache/vfs/{path}",
        has_data=has_data,
        data_size=data_size,
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


def test_overdue_entry_flagged_even_with_busy_queue():
    # A busy queue (uploading unrelated files) must not mask a single entry
    # forever: past the absolute overdue backstop (max(10x grace, 300s)) it is
    # flagged regardless of queue state.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)  # overdue = 300s
    entries = [_entry("gd/b.md", has_data=True)]
    mon.evaluate(_stats(queued=1), entries)
    clock.t = 120.0  # past grace but under overdue, queue busy → still ok (masked)
    assert mon.evaluate(_stats(queued=1), entries)["write_back_state"] == "ok"
    clock.t = 301.0  # past the overdue backstop → flagged despite busy queue
    health = mon.evaluate(_stats(queued=1), entries)
    assert health["write_back_state"] == "degraded"
    assert health["write_back_errors"][0]["reason"] == "dirty_entry_overdue"


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


def test_errored_uploads_surfaces_candidate_paths():
    # vfs/stats gives only a count; the error should name the current dirty
    # entries as candidates so the alert has something to point at.
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=_Clock())
    entries = [_entry("gd/a.md", has_data=True), _entry("gd/b.md", has_data=True)]
    health = mon.evaluate(_stats(errored=1), entries)
    err = [e for e in health["write_back_errors"] if e["reason"] == "errored_uploads"][0]
    assert err["candidate_paths"] == ["gd/a.md", "gd/b.md"]


def test_degraded_logs_once_per_episode_not_every_cycle(caplog):
    # A persistent stuck entry must log on transition, then stay quiet on
    # subsequent identical cycles (no 30s log spam).
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    entries = [_entry("gd/orphan.md", has_data=False)]
    mon.evaluate(_stats(), entries)       # t=0: establishes first-seen, not yet stuck
    clock.t = 31.0
    with caplog.at_level("INFO"):
        mon.evaluate(_stats(), entries)   # first degraded cycle → logs
        first = [r for r in caplog.records if '"write_back_degraded"' in r.message]
        clock.t = 61.0
        mon.evaluate(_stats(), entries)   # still degraded, same fault → no new log
        second = [r for r in caplog.records if '"write_back_degraded"' in r.message]
    assert len(first) == 1
    assert len(second) == 1  # unchanged — not re-logged


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


def test_stuck_entries_are_sorted():
    # os.walk order is not stable; the payload must be deterministic.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    entries = [_entry("gd/z.md", has_data=False), _entry("gd/a.md", has_data=False), _entry("gd/m.md", has_data=False)]
    mon.evaluate(_stats(), entries)
    clock.t = 31.0
    health = mon.evaluate(_stats(), entries)
    assert health["write_back"]["stuck_entries"] == ["gd/a.md", "gd/m.md", "gd/z.md"]


def test_scan_unavailable_preserves_state_and_degrades():
    # A failed cache scan must NOT reset per-path age tracking (which would mask a
    # stuck entry), and must surface as degraded, not silently "0 dirty / ok".
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0), clock=clock)
    entries = [_entry("gd/stuck.md", has_data=False)]
    mon.evaluate(_stats(), entries)          # t=0: entry seen, age clock started

    clock.t = 20.0
    unavail = mon.scan_unavailable(_stats(), "PermissionError: [Errno 13] /cache/vfsMeta")
    assert unavail["write_back_state"] == "degraded"
    assert unavail["write_back_errors"][0]["reason"] == "cache_scan_failed"
    # The underlying error travels with the report — "blind" must be diagnosable.
    assert "PermissionError" in unavail["write_back_errors"][0]["error"]
    assert unavail["write_back"]["dirty_entries"] is None  # unknown, not 0

    # State preserved: when the scan recovers past grace, the entry is correctly
    # flagged stuck — its age was NOT reset by the failed cycle.
    clock.t = 31.0
    health = mon.evaluate(_stats(), entries)
    assert health["write_back_state"] == "degraded"
    assert health["write_back"]["stuck_entries"] == ["gd/stuck.md"]


class _Cfg2(_Cfg):
    """Config stand-in for the collect_health_stats wiring tests."""

    cache_dir = "/nonexistent"
    rc_url = "http://127.0.0.1:5572"
    rc_timeout = 1


def test_collect_health_stats_scan_failure_does_not_reset(monkeypatch):
    # End-to-end wiring: _scan_dirty_entries returning None routes to
    # scan_unavailable rather than evaluate([]).
    import refresher

    monkeypatch.setattr(refresher, "read_vfs_stats", lambda cfg: _stats())
    monkeypatch.setattr(refresher, "_scan_dirty_entries", lambda cache_dir: (None, "PermissionError: nope"))
    mon = WriteBackMonitor(_Cfg2(), clock=_Clock())
    out = refresher.collect_health_stats(_Cfg2(), mon)
    assert out["write_back_state"] == "degraded"
    assert out["write_back_errors"][0]["reason"] == "cache_scan_failed"
    assert out["write_back_errors"][0]["error"] == "PermissionError: nope"


def test_unreadable_cache_is_never_reported_healthy_or_empty(tmp_path, monkeypatch):
    # The full path from a real permission error to a degraded report — the exact
    # deployed condition on 2026-07-26, where the sidecar (uid 65532) could not
    # read rclone's 0700 root-owned cache and reported everything healthy.
    import refresher

    cache = tmp_path / "cache"
    meta_root = cache / "vfsMeta" / "gd"
    meta_root.mkdir(parents=True)
    (meta_root / "stuck.md").write_text(json.dumps({"Dirty": True, "Size": 0, "Rs": None}))
    os.chmod(cache / "vfsMeta", 0o000)

    cfg = _Cfg2()
    cfg.cache_dir = str(cache)
    monkeypatch.setattr(refresher, "read_vfs_stats", lambda c: _stats())
    try:
        out = refresher.collect_health_stats(cfg, WriteBackMonitor(cfg, clock=_Clock()))
    finally:
        os.chmod(cache / "vfsMeta", 0o755)

    assert out["write_back_state"] == "degraded"          # never "ok"
    assert out["write_back"]["dirty_entries"] is None     # never 0
    assert out["write_back_errors"][0]["reason"] == "cache_scan_failed"


def test_readable_cache_scans_normally(tmp_path, monkeypatch):
    # The control case: a readable cache produces a real per-path scan.
    import refresher

    cache = tmp_path / "cache"
    (cache / "vfsMeta" / "gd").mkdir(parents=True)
    (cache / "vfsMeta" / "gd" / "a.md").write_text(json.dumps({"Dirty": True, "Size": 0, "Rs": None}))

    cfg = _Cfg2()
    cfg.cache_dir = str(cache)
    monkeypatch.setattr(refresher, "read_vfs_stats", lambda c: _stats())
    out = refresher.collect_health_stats(cfg, WriteBackMonitor(cfg, clock=_Clock()))

    assert out["write_back_state"] == "ok"
    assert out["write_back"]["dirty_entries"] == 1


def test_startup_selftest_logs_both_outcomes(tmp_path, caplog):
    # A deployment where detection cannot run must be loud at startup, not silent
    # until a write is lost. Both outcomes are logged explicitly.
    import refresher

    cache = tmp_path / "cache"
    (cache / "vfsMeta").mkdir(parents=True)
    cfg = _Cfg2()
    cfg.cache_dir = str(cache)

    with caplog.at_level("INFO"):
        assert refresher.cache_scan_selftest(cfg) is True
        os.chmod(cache / "vfsMeta", 0o000)
        try:
            assert refresher.cache_scan_selftest(cfg) is False
        finally:
            os.chmod(cache / "vfsMeta", 0o755)

    events = [json.loads(r.message)["event"] for r in caplog.records if r.message.startswith("{")]
    assert "cache_scan_selftest_ok" in events
    assert "cache_scan_selftest_failed" in events


# --- Handle-leak tolerance (dirty entries bounded regardless of open handles) ---


def test_pinned_by_handle_past_max_dirty_age_is_reported():
    # NFSv3 has no CLOSE: a task container torn down mid-mount leaves the entry
    # in-use forever, so the close-triggered write-back timer never fires and the
    # entry is never queued. This reproduces the observed production shape —
    # uploadsQueued:0 for the entire 24 hours, "in use 2" on every log line.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0, max_dirty_age=900.0), clock=clock)
    entries = [_entry("gd/pinned.md", has_data=True)]
    mon.evaluate(_stats(queued=0, in_progress=0), entries)

    # Past grace the generic "nothing is progressing" fires first...
    clock.t = 31.0
    assert mon.evaluate(_stats(), entries)["write_back_errors"][0]["reason"] == \
        "dirty_entry_not_progressing"

    # ...and past the maximum dirty age it escalates to the specific diagnosis,
    # which is what tells an operator to look for a leaked handle.
    clock.t = 901.0
    health = mon.evaluate(_stats(), entries)

    assert health["write_back_state"] == "degraded"
    err = health["write_back_errors"][0]
    assert err["reason"] == "dirty_entry_pinned_by_handle"
    assert err["path"] == "gd/pinned.md"
    assert err["max_dirty_age_seconds"] == 900.0
    assert health["write_back"]["max_dirty_age_seconds"] == 900.0


def test_pinned_bound_applies_regardless_of_open_handle_state():
    # The spec's core requirement: an abandoned mount must not silently strand a
    # write. Whatever the entry's in-use state, it is surfaced within the bound.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0, max_dirty_age=120.0), clock=clock)
    entries = [_entry("gd/abandoned.md", has_data=True)]
    mon.evaluate(_stats(), entries)
    clock.t = 121.0
    health = mon.evaluate(_stats(), entries)
    assert health["write_back"]["stuck_entries"] == ["gd/abandoned.md"]
    assert health["write_back_errors"][0]["reason"] == "dirty_entry_pinned_by_handle"


def test_entry_that_was_queued_is_not_called_pinned():
    # "Never queued" is what identifies the pinned case. An entry that WAS seen
    # queued and is merely slow is overdue, not pinned — different diagnosis,
    # different recovery.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0, max_dirty_age=900.0), clock=clock)
    entries = [_entry("gd/slow.md", has_data=True)]
    mon.evaluate(_stats(queued=1), entries)   # observed queued while dirty
    clock.t = 901.0
    health = mon.evaluate(_stats(queued=1), entries)
    assert health["write_back_errors"][0]["reason"] == "dirty_entry_overdue"


def test_max_dirty_age_is_configurable():
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0, max_dirty_age=60.0), clock=clock)
    entries = [_entry("gd/pinned.md", has_data=True)]
    mon.evaluate(_stats(), entries)
    clock.t = 45.0
    assert mon.evaluate(_stats(), entries)["write_back_errors"][0]["reason"] == \
        "dirty_entry_not_progressing"          # generic, below the bound
    clock.t = 61.0
    assert mon.evaluate(_stats(), entries)["write_back_errors"][0]["reason"] == \
        "dirty_entry_pinned_by_handle"         # specific, past the bound


def test_forcing_a_flush_is_off_by_default(caplog):
    # Reporting is the required behaviour; forcing must not happen unasked.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0, max_dirty_age=60.0), clock=clock)
    entries = [_entry("gd/pinned.md", has_data=True)]
    mon.evaluate(_stats(), entries)
    clock.t = 61.0
    with caplog.at_level("INFO"):
        mon.evaluate(_stats(), entries)
    events = [json.loads(r.message)["event"] for r in caplog.records if r.message.startswith("{")]
    assert "force_flush_unavailable" not in events


def test_forcing_a_flush_only_reacts_when_explicitly_enabled(caplog):
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(grace=30.0, max_dirty_age=60.0, force_flush=True), clock=clock)
    entries = [_entry("gd/pinned.md", has_data=True)]
    mon.evaluate(_stats(), entries)
    clock.t = 61.0
    with caplog.at_level("INFO"):
        mon.evaluate(_stats(), entries)
        clock.t = 91.0
        mon.evaluate(_stats(queued=1), entries)   # persistent fault → still one log
    logged = [json.loads(r.message) for r in caplog.records if r.message.startswith("{")]
    forced = [e for e in logged if e.get("event") == "force_flush_unavailable"]
    assert len(forced) == 1
    assert forced[0]["path"] == "gd/pinned.md"


# --- Write-back integrity (post-upload size verification) ---------------------


def _verifier(published_size):
    """Verifier stub: reports the size the cloud object was published with."""
    calls = []

    def verify(path, expected):
        calls.append((path, expected))
        return None if published_size is None else {"Size": published_size}

    verify.calls = calls
    return verify


def test_upload_size_mismatch_degrades_and_names_the_path():
    # rclone reported success but the published object is a different length
    # from the cached data that was uploaded — a bad publish, not a clean upload.
    clock = _Clock()
    verify = _verifier(1230)
    mon = WriteBackMonitor(_Cfg(), clock=clock, verifier=verify)
    mon.evaluate(_stats(), [_entry("gd/notes.md", has_data=True, data_size=16563)])
    health = mon.evaluate(_stats(), [])   # entry went clean → upload completed

    assert verify.calls == [("gd/notes.md", 16563)]
    assert health["write_back_state"] == "degraded"
    err = [e for e in health["write_back_errors"] if e["reason"] == "upload_size_mismatch"][0]
    assert err["path"] == "gd/notes.md"
    assert err["expected_size"] == 16563
    assert err["published_size"] == 1230
    assert health["write_back"]["size_mismatches"] == ["gd/notes.md"]


def test_upload_size_mismatch_persists_until_it_verifies_clean():
    # A one-cycle flash would be missed by a 30s-cadence alert; the condition
    # must hold until the path actually publishes correctly.
    clock = _Clock()
    verify = _verifier(1230)
    mon = WriteBackMonitor(_Cfg(), clock=clock, verifier=verify)
    mon.evaluate(_stats(), [_entry("gd/notes.md", has_data=True, data_size=16563)])
    mon.evaluate(_stats(), [])
    assert mon.evaluate(_stats(), [])["write_back_state"] == "degraded"   # still degraded

    # The path is rewritten and this time publishes at the right length.
    mon._verifier = _verifier(16563)
    mon.evaluate(_stats(), [_entry("gd/notes.md", has_data=True, data_size=16563)])
    assert mon.evaluate(_stats(), [])["write_back_state"] == "ok"


def test_matching_upload_size_is_healthy():
    clock = _Clock()
    verify = _verifier(460)
    mon = WriteBackMonitor(_Cfg(), clock=clock, verifier=verify)
    mon.evaluate(_stats(), [_entry("gd/ok.md", has_data=True, data_size=460)])
    health = mon.evaluate(_stats(), [])
    assert health["write_back_state"] == "ok"
    assert health["write_back"]["size_mismatches"] == []


def test_unstattable_published_object_is_unverified_not_degraded(caplog):
    # The file may simply have been deleted through the mount. Turning that into
    # an alert would make the check noise rather than signal.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(), clock=clock, verifier=_verifier(None))
    mon.evaluate(_stats(), [_entry("gd/gone.md", has_data=True, data_size=99)])
    with caplog.at_level("INFO"):
        health = mon.evaluate(_stats(), [])
    assert health["write_back_state"] == "ok"
    events = [json.loads(r.message)["event"] for r in caplog.records if r.message.startswith("{")]
    assert "upload_unverified" in events


def test_verification_is_skipped_when_disabled():
    # VERIFY_UPLOAD_SIZE=false wires no verifier at all — no extra stat per upload.
    clock = _Clock()
    mon = WriteBackMonitor(_Cfg(), clock=clock, verifier=None)
    mon.evaluate(_stats(), [_entry("gd/x.md", has_data=True, data_size=5)])
    health = mon.evaluate(_stats(), [])
    assert health["write_back_state"] == "ok"
    assert health["write_back"]["size_mismatches"] == []


def test_verification_failure_never_discards_local_content(tmp_path, monkeypatch):
    # The monitor is a read-only observer of the cache: a failed verification
    # must not remove or truncate the cached data (the only local copy).
    import refresher

    cache = tmp_path / "cache"
    data = cache / "vfs" / "gd" / "notes.md"
    data.parent.mkdir(parents=True)
    data.write_text("x" * 16563)
    (cache / "vfsMeta" / "gd").mkdir(parents=True)
    (cache / "vfsMeta" / "gd" / "notes.md").write_text(
        json.dumps({"Dirty": True, "Size": 16563, "Rs": [{"Pos": 0, "Size": 16563}]})
    )

    cfg = _Cfg2()
    cfg.cache_dir = str(cache)
    monkeypatch.setattr(refresher, "read_vfs_stats", lambda c: _stats())
    mon = WriteBackMonitor(cfg, clock=_Clock(), verifier=_verifier(1230))
    refresher.collect_health_stats(cfg, mon)
    # Entry goes clean; verification runs and fails.
    (cache / "vfsMeta" / "gd" / "notes.md").unlink()
    out = refresher.collect_health_stats(cfg, mon)

    assert out["write_back_state"] == "degraded"
    assert data.read_text() == "x" * 16563   # local content untouched


def test_stat_remote_object_builds_the_fs_and_relative_path(monkeypatch):
    import refresher

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"item": {"Size": 42}}

    def fake_post(url, json=None, timeout=None):
        captured.update(url=url, payload=json)
        return _Resp()

    monkeypatch.setattr(refresher.requests, "post", fake_post)

    cfg = _Cfg2()
    cfg.remote, cfg.folder = "gdrive", "Errand"
    assert refresher.stat_remote_object(cfg, "gdrive{a1b2}/notes/todo.md") == {"Size": 42}
    assert captured["url"].endswith("/operations/stat")
    assert captured["payload"] == {"fs": "gdrive:Errand", "remote": "notes/todo.md"}


def test_env_flag_parsing(monkeypatch):
    from refresher import _env_flag

    monkeypatch.delenv("X_FLAG", raising=False)
    assert _env_flag("X_FLAG", True) is True
    assert _env_flag("X_FLAG", False) is False
    for raw, expected in (("true", True), ("1", True), ("yes", True),
                          ("false", False), ("0", False), ("no", False), ("", True)):
        monkeypatch.setenv("X_FLAG", raw)
        assert _env_flag("X_FLAG", True) is expected


@pytest.mark.parametrize(
    "text,expected",
    [("1s", 1.0), ("500ms", 0.5), ("2m", 120.0), ("1h", 3600.0), ("5", 5.0), ("", 1.0), ("garbage", 1.0)],
)
def test_parse_duration(text, expected):
    assert _parse_duration(text, 1.0) == expected
