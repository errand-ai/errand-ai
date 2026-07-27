# Tasks

## 1. Restore monitor visibility (highest value — this is why the stall was silent)

- [x] 1.1 Reproduce the blindness in a test: assert `iter_dirty_entries` raises / `_scan_dirty_entries` returns `None` when the cache tree is unreadable by the scanning uid
      — **finding:** it did *neither*. `os.walk`'s default handler ignores an unreadable directory, so the scan returned `[]` and health read "0 dirty entries, ok" — a false-clean. `iter_dirty_entries` now propagates walk errors (`test_unreadable_cache_raises_rather_than_scanning_zero_entries`, `test_unreadable_subdirectory_also_raises`).
- [x] 1.2 Give the refresher read access to the cache: pod `fsGroup` + group-readable cache dirs, keeping the refresher at uid 65532
      — implemented as **matching uid** instead (see 1.3): `USER 65532` in `Dockerfile.gateway`, pod `securityContext` `runAsUser/runAsGroup/fsGroup: {{ workspace.runAsUser }}`.
- [x] 1.3 Verify empirically whether `fsGroup` covers directories rclone creates *after* mount on `local-path`; if not, add a `chgrp`/`chmod` in the gateway entrypoint after cache-dir creation (resolves an Open Question in design.md)
      — **verified empirically** against `rclone/rclone:1.68`: every cache directory is created `drwx------` (0700) at every level, inside an already-0755 `/cache`. Neither `fsGroup` nor a setgid bit nor an entrypoint `chmod` can help (they set ownership, not mode; and the dirs are created after serving starts). Matching uid is the only mechanism. design.md D1 + Open Questions updated.
- [x] 1.4 Make a failed cache scan a degraded, alertable condition: `write_back_state: "degraded"`, reason `cache_scan_failed`, underlying error included, structured log emitted
- [x] 1.5 Add a startup cache-scan self-test in the refresher that logs its outcome explicitly, so a deployment where detection cannot run is loud immediately (`cache_scan_selftest`)
- [x] 1.6 Tests: unreadable cache reports degraded (never healthy, never "no dirty entries"); readable cache scans normally; startup self-test logs both outcomes

## 2. Detect and repair metadata/data desync in the startup reconcile

- [x] 2.1 Add an inconsistency predicate to `cache_reconcile.py`: dirty entry with a non-empty data file whose metadata reports `Size: 0` / `Rs: null` (`DirtyEntry.is_inconsistent`)
- [x] 2.2 Implement metadata repair (set `Size` to the data file's actual length, `Rs` to the full extent) leaving the entry dirty so the complete content uploads — written via temp+rename so a crash mid-repair cannot truncate the metadata
- [x] 2.3 Implement the fingerprint guard: compare the entry's recorded remote fingerprint against the current cloud object; repair only when they still match (`fingerprint_matches`, `RcloneRemoteProbe` — shells out to rclone, since the rc API is not listening before serve)
      — **cache→remote path mapping was not what it looked like.** rclone keys the cache by the fs identity *and its full root* (`gdrive:Errand` → `vfs/gdrive{…}/Errand/…`; an alias expands to its backend and absolute path), so stripping one component addresses the wrong object whenever `workspace.folder` is set — which is the Helm default. Now resolved against a lazy, one-shot `rclone lsjson -R` listing by longest-suffix match, which also distinguishes found / absent / could-not-look. Verified end-to-end against real rclone 1.68: repair on match, quarantine on mismatch, data intact in both.
- [x] 2.4 Implement quarantine for entries failing the fingerprint guard — move aside within the PVC, retain content, emit a structured error naming path and mismatch. Also covers a remote that cannot be read at all (`remote_unverifiable`): publishing over an unverified remote is the risk this exists to prevent.
- [x] 2.5 Decide and implement the quarantine location (`.quarantine` sibling vs separate dir) and record it for the runbook (resolves an Open Question in design.md)
      — `<cache_dir>/quarantine/{vfs,vfsMeta}/<path>` + `manifest.jsonl`; sibling of the cache trees so rclone never sees it. Repeat quarantines suffix `.1`, `.2`. Runbook §6.
- [x] 2.6 Confirm reconcile still runs only before `rclone serve` starts, so repair never races a live cache (`entrypoint.sh` sequences it before `exec rclone`; asserted by `test_reconcile_receives_the_serve_target`)
- [x] 2.7 Tests using the real production signature (`Size: 0`, `Rs: null`, 56254-byte data file): repaired when fingerprint matches; quarantined when it does not; data file never deleted in either path
- [x] 2.8 Regression test: an entry with an *absent* data file is still reconciled as before (do not break the existing orphan path)

## 3. Write-back integrity — never publish a partial object

- [x] 3.1 Add post-upload size verification: compare the cloud object's size against the uploaded cached data's size
      — implemented in the **refresher** (rclone owns the upload path; nothing of ours sits in it): the cached length is recorded while the entry is dirty and checked via rc `operations/stat` when the entry goes clean.
- [~] 3.2 On mismatch, treat as upload failure — retry per existing policy, do not clear the dirty flag, do not discard cached data
      — **partially achievable.** Cached data is never discarded (the monitor only reads the cache) and the mismatch is held as a live fault. The *retry* half is rclone's own: it retries genuine upload failures, but a false-success mismatch cannot be pushed back into rclone's upload queue from outside the process. Reported rather than silently retried; recovery is runbook §5.4.
- [x] 3.3 On persistent mismatch, surface degraded write-back health with a structured error naming the path — the mismatch persists until the path verifies clean again, so it cannot flash between two 30s health cycles
- [x] 3.4 Make verification toggleable in case the extra `operations/stat` per upload proves costly (`VERIFY_UPLOAD_SIZE` / `workspace.writeBackHealth.verifyUploadSize`)
- [x] 3.5 Decide whether verification also covers pre-existing cached entries at startup (would have caught this incident's corruption from the *previous* process) — resolves an Open Question in design.md
      — **yes, via the reconcile's fingerprint guard** (2.3) rather than a separate size pass: every dirty entry at startup is already stat'd against the cloud object, comparing hash and modtime as well as size, at no extra cost.
- [x] 3.6 Tests: size mismatch retains the dirty entry and degrades; matching size clears it; verification failure never discards local content

## 4. Bound dirty age regardless of open-handle state

- [x] 4.1 Add a `dirty_entry_pinned_by_handle` classification to `WriteBackMonitor.evaluate` as a fourth stuck reason
- [x] 4.2 Add an operator-configurable maximum dirty age, independent of the close-triggered write-back delay (`MAX_DIRTY_AGE_SECONDS` / `workspace.writeBackHealth.maxDirtyAgeSeconds`, default 900s)
- [~] 4.3 Report (do not force-flush) by default; add an explicit opt-in flag for forcing, defaulted off
      — reporting and the default-off flag are implemented. **Forcing has no safe mechanism:** rclone's rc API exposes no way to flush a dirty item that was never queued (`vfs/queue-set-expiry` only reorders already-queued items). Enabling `FORCE_FLUSH_PINNED` logs `force_flush_unavailable` and still reports, rather than reaching around the VFS to publish a file a client may still be writing. Recovery is runbook §5.3.
- [x] 4.4 Tests: an entry dirty past the bound and never queued while in-use is reported degraded; forcing stays off unless explicitly enabled

## 5. Eliminate the interactive OAuth path (existing requirement, never met)

- [x] 5.1 Confirm the mechanism: rclone's OAuth redirect listener holds `127.0.0.1:53682` for the process lifetime, so every refresher `config/update` fails `bind: address already in use`
      — mechanism accepted from the incident evidence; the *fix* is verified by test. Live confirmation on the cluster is 5.4.
- [x] 5.2 Ensure the writable rclone config contains a complete, usable token before `rclone serve` starts (the refresher's existing `init` mode — unchanged, now enforced by 5.3)
- [x] 5.3 Make the gateway entrypoint verify a usable token is present and fail fast rather than letting rclone fall through to the interactive flow; also exports `RCLONE_AUTH_NO_OPEN_BROWSER`
- [ ] 5.4 Verify no process listens on 53682 after startup, and that a refresher `config/update` succeeds against a running gateway — **needs the cluster** (commands in runbook §8)
- [x] 5.5 Test: a config missing a usable token causes a loud startup failure, not a degraded start that squats the port (plus empty-token and wrong-remote cases)

## 6. Operational runbook

- [x] 6.1 Write `docs/workspace-gateway-runbook.md`
- [x] 6.2 Document the safe take-down procedure: suspend ArgoCD auto-sync **first** — an unsuspended `kubectl scale` is reverted within seconds and the resulting restart flushes dirty entries (this is how the 2026-07-26 corruption was triggered) — §2
- [x] 6.3 Document confirming no task-runner pods are mounting the export before maintenance — §2.1
- [x] 6.4 Document the mandatory backup-both-sides step before any reconcile or restart, with the verification commands (size + md5, cache side and cloud side) — §3
- [x] 6.5 Document how to detect a stalled write-back (`vfs/stats`, dirty-entry scan, health state) and how to recover content from a stalled or quarantined entry — §4, §5, §6
- [x] 6.6 Document the second-writer hazard: a desktop sync client on the same folder is unsupported per spec, and note that one is currently active on `workflow/` — §7

## 7. Helm and deployment

- [x] 7.1 Wire new tunables into the chart: maximum dirty age, force-flush opt-in, size-verification toggle (`workspace.writeBackHealth.*`)
- [x] 7.2 Add the `fsGroup` / cache-permission changes to the gateway pod spec (pod `securityContext` with matching `runAsUser`/`runAsGroup`/`fsGroup`; `workspace.runAsUser`)
- [x] 7.3 Bump `VERSION` per semver (minor — new behaviour, backwards compatible): 0.137.0 → 0.138.0

## 8. Verification

- [x] 8.1 Run the full test suite: `errand/.venv/bin/python -m pytest workspace-gateway/tests/ -v` — 79 passed (44 → 79)
- [ ] 8.2 Local stack check via `docker compose -f testing/docker-compose.yml up --build` — the gateway image builds and was verified directly (runs as 65532; `/cache` writable; rclone creates its cache `0700 gateway:gateway`). The full `--profile workspace` stack needs an authorised `rclone.conf` and a workspace bearer.
- [ ] 8.3 End-to-end on the cluster, following the runbook from task 6: write through the mount, confirm it reaches Drive within the write-back delay, confirm no dirty entries remain — **needs the cluster + a maintenance window**
- [ ] 8.4 Negative test on the cluster: induce a stalled entry and confirm the gateway reports degraded with the path named — the behaviour that was missing on 2026-07-26 — **needs the cluster**
- [ ] 8.5 Confirm the refresher logs a successful startup cache scan in the deployed pod (the single check that would have caught this incident on day one) — **needs the cluster** (`grep cache_scan_selftest`, runbook §4.4)

### Pre-deployment note

Deploying this on an existing gateway leaves the cache PVC owned by **root** from
the previous version, so the newly non-root rclone cannot write it. `fsGroup`
re-owns the volume to gid 65532 on mount, which covers it — but confirm
`cache_scan_selftest_ok` in the refresher logs immediately after the rollout
(runbook §4.4). Locally, an existing `workspace-cache` Docker volume must be
removed (`docker volume rm testing_workspace-cache`).
