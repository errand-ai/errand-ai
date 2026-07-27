## Context

The workspace gateway is a two-container pod: `rclone serve nfs` against a Drive/OneDrive folder with `--vfs-cache-mode full` on a persistent PVC, plus a `refresher` sidecar that rotates the cloud token via the loopback rc API and monitors write-back health. Task-runner pods mount the NFS export at `/shared`.

The previous change (`2026-07-25-workspace-gateway-write-reliability`, archived) added the write-reliability requirements to the spec and implemented `cache_reconcile.py` and `refresher.py`'s `WriteBackMonitor`. One day later, production stalled for 24+ hours with none of that machinery firing. Investigation established that the code is largely correct and the *deployment* defeats it.

Observed state during the stall:

```
vfsMeta/gdrive{…}/workflow/BlogsToProcess.md
    {"ModTime": "…19:55:59Z", "Size": 0, "Rs": null,
     "Fingerprint": "63805,…19:28:15Z,2bbf85b7…", "Dirty": true}
vfs/gdrive{…}/workflow/BlogsToProcess.md          → 56254 bytes present
vfs/stats  → uploadsQueued: 0, uploadsInProgress: 0, erroredFiles: 0
rclone log → "in use 2" on every line for 24h; zero mentions of either file
```

A healthy entry for comparison carries `Size: 460`, `Rs: [{Pos:0,Size:460}]`, `Dirty: false`.

Four distinct defects compound into silent data loss:

1. **The refresher cannot read the cache.** It runs as uid 65532; rclone (root) creates `/cache/vfs` and `/cache/vfsMeta` mode `0700 root:root`. `iter_dirty_entries` raises `PermissionError`, `_scan_dirty_entries` returns `None`, `collect_health_stats` skips `evaluate()`. Detection is inert.
2. **A failed scan is silent.** `None` correctly avoids a false-clean reading but logs nothing, so "blind" looks identical to "healthy".
3. **The reconcile's orphan definition misses metadata/data desync.** It orphans only entries whose data file is *absent*; the production signature had data present with `Size: 0` metadata, so it was preserved as "resumable" — then published as a partial write.
4. **Handles leak, so write-back never fires.** NFSv3 has no `CLOSE`; `--vfs-write-back` starts its timer on close. A task-runner torn down mid-mount leaves the entry permanently `in use`, so the entry is never queued in the first place.

Separately, rclone enters an interactive OAuth flow at startup and its redirect webserver holds `127.0.0.1:53682` for the process lifetime, so every refresher `config/update` fails `bind: address already in use`. The refresher has never successfully rotated a token; rclone's internal refresh masks it.

## Goals / Non-Goals

**Goals:**

- A dirty entry can never remain unuploaded and unreported. Either it uploads, or the gateway reports degraded with the path named.
- The monitor's own failure is itself an alertable condition — no silent blindness.
- An upload publishes the complete cached content or fails; never a partial object.
- Write-back progresses regardless of open-handle state.
- The refresher's `config/update` path works, so token rotation is real rather than incidentally masked.
- A documented, safe maintenance procedure for an ArgoCD-managed gateway.

**Non-Goals:**

- Changing ArgoCD behaviour or sync policy. Out of scope by decision; the runbook documents working *with* self-heal.
- Replacing NFS with another transport, or moving off rclone.
- Resolving the second-writer hazard (a Drive desktop client syncing the same folder). Recorded as known risk in the proposal; needs its own decision about folder scoping.
- Recovering the specific files from the 2026-07-26 incident — already done manually.

## Decisions

### D1. Give the refresher read access to the cache rather than moving the scan into rclone

The scan must see `/cache/vfsMeta`. Options considered:

- **Run the refresher as root.** Simplest, but regresses the container's security posture for a read-only need.
- **Move detection into the gateway container.** rclone's image is not ours to extend cheaply, and the refresher already owns health reporting; splitting it separates related logic.
- **Shared gid + group-readable cache.** Run both containers with a shared supplementary group and set the cache dirs group-readable (`fsGroup` on the pod plus `0750`/`0640`).
- **Chosen (revised during implementation): matching uid.** Run *both* containers as uid 65532.

**Why the group approach was rejected.** rclone creates its VFS cache directories with mode `0700` — evidenced directly by the incident (`0700 root:root`). Mode `0700` grants the group nothing, so no `fsGroup`/setgid arrangement can make the tree readable: `fsGroup` and the setgid bit control *ownership* of newly created entries, not their mode, and rclone's `0700` overrides any umask. An entrypoint `chmod` cannot help either, because the directories that matter are created by rclone *after* serving starts. The spec's requirement is "matching uid/gid, **or** group-readable cache"; only the first branch is achievable, so both containers now run as 65532 (`workspace.runAsUser`, `USER 65532` in `Dockerfile.gateway`, pod `securityContext` with `fsGroup` so the PVC is writable by them).

The startup self-test (D2) remains the authority: it verifies the access rather than assuming it, and is what makes getting this wrong loud instead of silent.

### D2. Treat "cannot scan" as degraded, not as "nothing to report"

`_scan_dirty_entries` returning `None` currently leads to skipping evaluation. It must instead set `write_back_state: "degraded"` with reason `cache_scan_failed`, including the underlying error, and emit a structured log. This converts the exact failure that hid this incident into an alert.

A startup self-test is stronger than waiting for the first cycle: on start the refresher SHALL attempt one scan and log its outcome explicitly, so a misconfigured deployment is loud immediately rather than silent until something breaks.

### D3. Extend reconcile to metadata/data desync, and repair rather than delete

The reconcile currently asks "is there data to upload?". It must also ask "does the metadata agree with the data?". An entry with a non-empty data file but `Size: 0` / `Rs: null` is inconsistent and unsafe to upload as-is.

The safe action is **not** deletion — the data file held the only copy of real user work (22 lines of completed task output). Options:

- **Delete the entry** (current behaviour for absent-data orphans): correct when there is nothing to lose, catastrophic here.
- **Chosen: repair the metadata** to match the data file (`Size` := actual length, `Rs` := single full-range), leaving the entry dirty so rclone uploads the complete content.
- **Quarantine** (move aside and log) as the fallback when the entry cannot be safely repaired.

Repair is only safe while the gateway is the sole writer. If the remote fingerprint has changed underneath the dirty entry, repairing and uploading would overwrite a newer remote object. In that case the entry SHALL be quarantined and reported, not uploaded — this is the concurrent-writer case the existing spec already calls unsupported, and the incident showed it is not theoretical.

### D4. Verify uploads by size, and never publish a partial object

The corruption was a same-length file with the new content written over the head of a stale buffer and the old tail retained, breaking a line mid-word. Any integrity check must therefore compare against the *cached entry*, not merely check that the object is non-empty or unchanged in length.

After an upload completes, the gateway SHALL compare the remote object's size to the cached entry's size and treat a mismatch as an upload failure (retry, then degrade). Size is chosen over checksum because Drive exposes it cheaply on `operations/stat`; a checksum comparison is a possible strengthening if the provider makes one available without a re-read.

The stronger guarantee — atomic replace via upload-to-temp-then-rename — is preferred where the backend supports it, but Drive's semantics make this awkward and it is not required to close the observed defect. Size verification plus refusal to upload from inconsistent metadata (D3) removes the mechanism that produced the corruption.

### D5. Bound dirty age independently of open-handle state

`--vfs-write-back` is close-triggered and NFSv3 never closes. Rather than fight rclone's semantics, the gateway SHALL enforce an upper bound on how long an entry may stay dirty: past a configurable maximum, the entry is flushed regardless of `in use`, or if that is not achievable through the rc API, reported as degraded with reason `dirty_entry_pinned_by_handle`.

Detection is achievable today and is the minimum bar — a pinned entry must never be silently exempt. Forcing a flush of a file another process may still be writing risks publishing a torn state, which is precisely the failure this change exists to prevent, so **reporting is the required behaviour and forcing is opt-in**. The existing `WriteBackMonitor` already has the machinery: `is_orphaned` / `queue_idle` / `overdue` classification needs a fourth reason rather than a new subsystem.

### D6. Eliminate the interactive OAuth path at startup

rclone starts the OAuth redirect listener because the config it is given looks like it needs interactive authorisation. The fix is to ensure a complete, valid token is present in the writable config *before* `rclone serve` starts — which is what the refresher's `init` mode already exists to do — and to fail loudly if it is not, rather than letting rclone fall through to the interactive flow and squat the port.

The gateway entrypoint SHALL verify the config contains a usable token before serving, and the deployment SHALL treat a missing token at startup as a fatal error rather than a degraded start.

## Risks / Trade-offs

- **Metadata repair writes into rclone's private cache format** → Only performed by the startup reconcile while `rclone serve` is *not* running (the entrypoint already sequences it this way), never against a live cache. Format is version-coupled to the rclone image; pin the image and cover the metadata shape in tests.
- **Repair could publish stale content over a newer remote object** → Guarded by the fingerprint check in D3; quarantine rather than upload when the remote has moved. This is the incident's second file exactly, and it corrupted real data.
- **`fsGroup` may not cover directories rclone creates post-mount** → Verify at runtime via the D2 startup self-test; entrypoint `chgrp` fallback if needed. The self-test is what makes this safe to get wrong.
- **Forcing a flush of a pinned entry could publish a partially-written file** → Which is why forcing is opt-in and reporting is the default. A stalled-but-reported write is recoverable; a torn published write may not be.
- **Size verification adds a round-trip per upload** → One `operations/stat` per completed upload, on a low-volume workspace. Acceptable; make it toggleable if it proves costly.
- **More alerting surface could produce noise** → The new conditions are all genuinely actionable (blind monitor, pinned entry, size mismatch). Grace periods and the existing overdue backstop already damp transients.

## Migration Plan

No data migration; behaviour is confined to the gateway pod and its cache PVC.

1. Ship the reconcile and refresher changes together — the reconcile repairs desynced entries at startup, and the refresher must be able to see the cache to confirm the result.
2. Deploy during a window with no task-runner pods running (the runbook covers detecting this).
3. Because the deployment is ArgoCD-managed with self-heal, follow the runbook rather than `kubectl scale` — an unsuspended scale-down is reverted within seconds and the resulting restart flushes dirty entries. This is not hypothetical: it is how the 2026-07-26 corruption was triggered.
4. Verify post-deploy: refresher logs a successful startup cache scan; `vfs/stats` reachable; a test write through the mount reaches the cloud within the write-back delay; no dirty entries left after it lands.

Rollback is a normal image revert. The reconcile's repair step is the only forward-only action; entries it repairs are left in a state prior rclone versions read normally.

## Open Questions

All three were resolved during implementation; recorded here with their answers.

- ~~Does `fsGroup` reliably cover rclone-created cache subdirectories on this storage class (`local-path`), or is an entrypoint `chgrp` required?~~ **Resolved: neither works.** rclone creates cache directories mode `0700`, which grants the group nothing regardless of ownership, and it creates them *after* serving starts so an entrypoint `chmod` cannot reach them. Both containers now run as the same uid (65532). See the revised D1.
- ~~Should the size-verification check cover pre-existing uploads on startup, or only uploads this process performs?~~ **Resolved: startup coverage is provided by the reconcile's fingerprint guard (D3), not by a separate size pass.** Every dirty entry at startup is already stat'd against the cloud object, which is a stronger check than size alone (it compares hash and modtime too) and costs nothing extra — the stat is needed anyway to decide repair vs quarantine. Clean cached entries are not re-verified: they carry no pending write, so a mismatch there is a cache-staleness question for change-polling, not a write-back integrity one.
- ~~Is quarantine (D3) a separate cache location, or a `.quarantine` sibling within the PVC?~~ **Resolved: `<cache_dir>/quarantine/`**, a sibling of `vfs/` and `vfsMeta/` (not inside either, so rclone never sees quarantined items as cache content). It mirrors the cache layout — `quarantine/vfs/<path>` and `quarantine/vfsMeta/<path>` — so an operator recovers content by its familiar path, plus `quarantine/manifest.jsonl` recording path, reason, sizes and timestamp per entry. Repeat quarantines of one path suffix with `.1`, `.2`, … rather than overwriting an earlier rescue copy. Documented in §6 of the runbook.

## Implementation notes (deviations worth recording)

- **The blindness was worse than assumed.** design.md described `iter_dirty_entries` raising `PermissionError`. In fact `os.walk`'s default error handler *ignores* an unreadable directory, so the scan returned an empty list and the monitor reported "0 dirty entries, healthy" — a false-clean, not a detectable failure. `iter_dirty_entries` now propagates walk errors so the caller can report `cache_scan_failed`.
- **Cache paths do not map to remote paths the obvious way.** rclone keys the VFS cache by the fs's identity *and its full root*, so serving `gdrive:Errand` caches `notes/a.txt` at `vfs/gdrive{…}/Errand/notes/a.txt`, and an alias remote expands to its underlying backend and absolute path (`loc:Errand` → `vfs/local/tmp/data/Errand/…`, verified against rclone 1.68). The prefix depth is therefore not derivable from the serve target. The fingerprint guard resolves paths against a real `rclone lsjson -R` listing of the serve root — loaded lazily, once, and only when an entry actually needs verifying — matching the longest suffix that names an object. This also yields a three-way outcome (found / absent / could-not-look) that a per-path stat could not distinguish, which is what makes "brand-new file, nothing to overwrite → repair" separable from "it was deleted under us → quarantine".
- **Post-upload verification lives in the refresher, not "the gateway".** rclone performs the uploads; nothing in our code sits in that path. The refresher verifies a path's published size when the entry goes clean, and reports a mismatch as degraded until it verifies clean again. The retry half of D4 is rclone's own (it retries genuine upload *failures*); a false-success mismatch cannot be pushed back into rclone's upload queue from outside, so it is reported rather than silently retried.
- **Blindness hid one level up too (found in review).** `os.path.isdir` also swallows `PermissionError` and returns False, so an unreadable *cache root* — as distinct from an unreadable `vfsMeta` — still yielded zero entries silently. The scan now lists the cache root itself, and `meta_root_present` distinguishes "rclone hasn't created the tree yet" from "we can't see it". Relatedly, the startup self-test is no longer one-shot: both containers start together, so on a fresh PVC it would have logged `ok` on a cache rclone had not populated — passing on exactly the deployment it exists to catch. It now reports `pending` and rechecks each health cycle until visibility is genuinely proven.
- **Size verification needed a settling rule (found in review).** The cached data file grows as the NFS client writes it, so a single mid-write sample is a partial length; comparing the complete published object against it would report a mismatch on a good upload. A length is only eligible once observed twice unchanged, and unresolved mismatches are capped so the health payload cannot grow without bound.
- **The path-mapping fix had to be applied twice (found in review).** `stat_remote_object` in the refresher still used the discarded one-component-strip model, which would have made post-upload verification permanently inert whenever `workspace.folder` was set — the Helm default. The two call sites resolve differently on purpose: the reconcile uses the authoritative listing because a wrong answer there strands or destroys data, while the refresher derives the prefix from the configured folder (`fs.Name() + "/" + fs.Root()`) because it cannot afford a recursive listing per health cycle and a wrong answer only degrades to "unverified".
- **Force-flushing a pinned entry has no safe mechanism.** rclone's rc API exposes no way to flush a dirty item that was never queued (`vfs/queue-set-expiry` only reorders items already in the queue). The opt-in flag exists and defaults off as the spec requires; when enabled it logs `force_flush_unavailable` and still reports rather than reaching around the VFS to publish a file a client may still be writing. Recovery is the runbook procedure (§5.3).
