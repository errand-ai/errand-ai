## Why

On 2026-07-26 the workspace gateway silently stopped syncing task writes to Google Drive for over 24 hours. Two files sat in the VFS cache marked `Dirty: true` with `Size: 0`, never queued for upload, while `vfs/stats` reported `uploadsQueued: 0` and `erroredFiles: 0`. Task-runner pods read and wrote through the mount normally, so the stall was invisible from every side: no error, no degraded health, no failed task. Twenty-two lines of completed task work existed only inside the cache PVC.

When the gateway was later restarted, the startup reconcile logged `reconciled: 0` despite two orphaned dirty entries being present, then uploaded one of them as a **partial write** — the new 1230-byte content written over the head of a stale 16563-byte buffer, leaving the old tail in place and a line broken mid-word. The result was a same-length, corrupted file in the user's Drive. Recovery was only possible because backups had been taken by hand first.

The `workspace-gateway` specification already requires nearly all of the behaviour that was missing — including, almost verbatim, the exact fault signature observed (`Dirty:true, Size:0` with `uploadsQueued:0`) and the requirement that it "SHALL be detected and surfaced, never left silent". This change is therefore primarily about **bringing the implementation into conformance with requirements that already exist**, plus closing two genuine specification gaps that tonight's incident exposed.

## What Changes

**Conformance with existing requirements (implementation gaps):**

The stuck-upload detection required by "Write-back health and stuck-upload detection" **is implemented** in `refresher.py` (`WriteBackMonitor.evaluate`) and its logic is correct for the observed fault. It never ran, for two compounding reasons:

- **The refresher cannot read the VFS cache.** It runs as uid 65532 while rclone (root) creates `/cache/vfs` and `/cache/vfsMeta` mode `0700 root:root`. `iter_dirty_entries` fails with `Permission denied`, `_scan_dirty_entries` returns `None`, and `collect_health_stats` skips `evaluate()` entirely. The entire detection mechanism is inert in the deployed configuration. The two containers SHALL share a filesystem identity (matching uid/gid, or group-readable cache) so the scan can run.
- **A failed cache scan is silent.** Returning `None` correctly avoids the false-clean reading, but nothing is logged, so "detection is blind" is indistinguishable from "nothing is wrong". A persistent scan failure SHALL itself be a degraded, alertable condition — otherwise the monitor's own failure mode is the same silent data loss it exists to prevent.

- **The startup reconcile's orphan definition is too narrow.** `cache_reconcile.py` treats an entry as orphaned only when its data file is *absent*. The production signature was `Dirty: true` with `Size: 0` and `Rs: null` in the metadata while a **non-empty data file was present** (56254 and 16563 bytes). That is classified as "a resumable upload; leave it", producing `reconciled: 0` with two faulted entries present — after which rclone published a partial write from the inconsistent metadata. Detection SHALL cover metadata/data desync, not just missing data.
- Stop rclone entering an interactive OAuth flow at startup. The existing token-refresher requirement already forbids any form that triggers it; because it does, rclone's OAuth redirect webserver holds `127.0.0.1:53682` for the process lifetime and every subsequent `config/update` fails with `bind: address already in use`. The refresher has therefore never successfully rotated a token. This is currently masked by rclone's own internal refresh and becomes an outage when the refresh token needs rotating.

**New requirements (specification gaps):**

- **Write-back integrity.** An upload SHALL replace the cloud object atomically with the complete cached content, or fail. A partial or length-mismatched write SHALL never be published. The gateway SHALL verify the uploaded object's size against the cached entry and treat a mismatch as an upload failure. This failure mode is not currently forbidden by any requirement, and it is the one that caused real data corruption.
- **Handle-leak tolerance.** A cache entry SHALL NOT be exempted from write-back or from stuck-upload detection solely because it is held open. NFSv3 has no `CLOSE` operation, so a task-runner pod torn down mid-mount leaves the entry permanently `in use` and `--vfs-write-back` — which starts its timer on close — never fires. The gateway SHALL bound how long a dirty entry may remain unflushed regardless of open-handle state.

**Operational documentation:**

- An operational runbook for gateway maintenance covering the safe procedure for taking the gateway down (the deployment is ArgoCD-managed with self-heal; a bare `kubectl scale` is reverted within seconds and the resulting restart flushes dirty entries), how to detect and recover a stalled write-back, and the backup-before-reconcile sequence. ArgoCD behaviour itself is explicitly **out of scope** as a spec concern and is covered by the runbook only.

## Capabilities

### New Capabilities

None. All behaviour belongs to the existing `workspace-gateway` capability.

### Modified Capabilities

- `workspace-gateway`: adds two requirements — write-back integrity (atomic, size-verified uploads; no partial publish) and handle-leak tolerance (dirty entries bounded regardless of open-handle state). Extends the existing "Write-back health and stuck-upload detection" and "Gateway runs as a restart-managed, crash-resilient workload" requirements with a documented maintenance procedure for an ArgoCD-managed deployment.

## Impact

- **`errand-workspace-gateway` image** — rclone container startup (eliminate the interactive OAuth path that squats 53682); write-back integrity verification.
- **`errand-workspace-refresher` image** — stuck-upload monitoring loop against `vfs/stats`; health state extended beyond auth to write-back; structured alertable logging for both.
- **Startup reconcile** — orphaned-dirty-entry detection currently returns zero when entries are present.
- **Helm chart** — any new tunables (grace period, integrity-check toggle) and health/probe wiring.
- **Docs** — new gateway operational runbook.
- **No API or data-model change.** No migration. Behaviour is confined to the gateway pod and its cache PVC.

### Known adjacent risk (not addressed here)

The existing requirement "Gateway is the sole writer of task-written paths" declares a second sync client on the same cloud folder unsupported. A Google Drive desktop client is currently syncing the same `workflow/` folder the gateway serves. Tonight's recovery depended on that client for read/write access to Drive, but per the spec it is a standing hazard capable of overwriting a gateway write-back. Flagged here deliberately; resolving it is a separate decision about folder scoping.
