# Shared-workspace gateway

`rclone serve nfs` against a single Google Drive / OneDrive folder, exposed over
NFSv3 for task containers to mount at `/shared`. A token-refresher sidecar keeps
the running rclone authenticated and reports gateway health back to errand.

- `entrypoint.sh` — the gateway container entrypoint (rclone serve wrapper).
- `cache_reconcile.py` — startup reconcile of faulted dirty VFS-cache entries,
  and the shared dirty-entry scanner used by health monitoring.
- `refresher.py` — token-refresher + health sidecar.

Operating it — safe take-down, detecting a stall, recovering content — is
documented in [`docs/workspace-gateway-runbook.md`](../docs/workspace-gateway-runbook.md).

## Both containers run as uid 65532 — and must

rclone creates its VFS cache directories mode `0700`, so **only the creating uid
can read them**. The refresher's dirty-entry scan is therefore possible only when
it shares rclone's uid. When rclone ran as root and the refresher as 65532, the
scan walked an unreadable tree, found nothing, and reported "no dirty entries,
healthy" — while two completed writes sat unuploaded for 24 hours (2026-07-26).

A shared *group* cannot fix this: `0700` grants the group nothing, and `fsGroup`
/ setgid control ownership, not mode. The uid must match. It is pinned in three
places that must stay in agreement: `USER 65532` in both Dockerfiles, the pod
`securityContext` (`workspace.runAsUser`), and the compose services. The
refresher's startup self-test (`cache_scan_selftest_ok` / `_failed`) is the
authority — check it after any change here.

## Write-back reliability

Task writes reach the cloud through rclone's `--vfs-cache-mode full` write-back:
`close()` → the VFS item is marked dirty and its data cached → write-back uploads
it. The gateway tunes and guards that last hop:

- **Prompt, tunable write-back.** `--vfs-write-back` is set explicitly and short
  (default `1s`, `workspace.cache.writeBack`) instead of rclone's implicit 5s, to
  bound the window in which a completed write can be lost before it uploads.
  `--transfers` / `--low-level-retries` / `--retries` keep a transient provider
  error in a *retrying* state rather than dropping the write.
- **Never drop a dirty entry.** `--vfs-cache-mode full` never evicts a dirty
  (not-yet-uploaded) entry under `--vfs-cache-max-size` pressure — a completed
  write is retained until its upload succeeds.
- **Faulted-entry recovery on restart.** On start, before serving (never against
  a live cache), `cache_reconcile.py` handles two fault shapes:
  - *orphaned* — dirty meta with **no data file**: the stale meta is cleared, so
    rclone re-fetches the current cloud object on the first poll instead of
    blocking change-polling or uploading an empty file;
  - *desynced* — dirty meta reporting `Size: 0` / `Rs: null` while a **non-empty
    data file exists**: the metadata is **repaired** to match the data (so the
    complete content uploads) when the recorded remote fingerprint still matches
    the cloud object, and **quarantined** when it does not, or cannot be checked.
    Uploading from a desynced entry is what published a corrupted, same-length
    file over a user's document on 2026-07-26. The data file is never deleted to
    resolve an inconsistency — it may be the only copy of completed work.
- **Write-back health.** The refresher polls `vfs/stats` and scans the VFS cache
  each health cycle. Any of the following moves write-back health to `degraded`
  and emits a structured, alertable error naming the path, in the same health
  state used for auth-refresh failures: a dirty entry past the grace period
  (`max(3 × writeBack, 30s)`) without progressing; a dirty entry past
  `maxDirtyAgeSeconds` that was never queued (**pinned by a leaked NFS handle** —
  NFSv3 has no `CLOSE`, so the close-triggered write-back timer never fires); a
  non-zero `erroredFiles` count; or a completed upload whose **published size
  differs** from the cached data uploaded. Detection is in-band; it does not
  depend on external monitoring.
- **A blind monitor is itself a fault.** A cache the refresher cannot scan is
  reported `degraded` with the underlying error — never as healthy, and never as
  "no dirty entries". A startup self-test makes a deployment where detection
  cannot run loud on day one.
- **No interactive OAuth at startup.** The gateway refuses to start without a
  usable token for its remote. rclone would otherwise open an OAuth redirect
  listener that holds `127.0.0.1:53682` for the process lifetime, making every
  refresher `rclone rc config/update` fail with `bind: address already in use` —
  token rotation would silently never happen.

### Provider cadence

Google Drive and OneDrive have different change/upload latencies. `writeBack`
(and `workspace.pollInterval`, the F6 poll-interval cadence) may warrant
different values per provider; the defaults are tuned for Google Drive. Validate
per provider.

## The gateway is the sole writer of task-written paths

For any path that tasks write through `/shared`, **the cloud folder is owned by
the gateway.** A second sync client writing the same paths concurrently — e.g. a
person's native Google Drive or OneDrive desktop client syncing the same
folder — is **unsupported**. Two independent writers of the same cloud object
cannot be safely arbitrated: the native client has no notion of the gateway's
in-flight dirty state, and vice-versa. The concrete failure modes are:

- an external re-upload of an older copy **overwrites a gateway write-back**, or
- the gateway's change-poll sees the object change underneath a locally-dirty
  entry and **discards the local dirty write**.

Scope the cloud folder to gateway-owned content, or exclude task-written subpaths
from any other sync client. As the observable symptom of a second writer, the
gateway logs a structured `concurrent_writer_detected` warning (naming the path)
when a locally-dirty object's remote fingerprint changes underneath it. The
gateway detects and surfaces this conflict; it does **not** attempt a three-way
merge.
