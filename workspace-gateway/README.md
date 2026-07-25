# Shared-workspace gateway

`rclone serve nfs` against a single Google Drive / OneDrive folder, exposed over
NFSv3 for task containers to mount at `/shared`. A token-refresher sidecar keeps
the running rclone authenticated and reports gateway health back to errand.

- `entrypoint.sh` — the gateway container entrypoint (rclone serve wrapper).
- `cache_reconcile.py` — startup reconcile of orphaned dirty VFS-cache entries,
  and the shared dirty-entry scanner used by health monitoring.
- `refresher.py` — token-refresher + health sidecar.

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
- **Orphaned-entry recovery on restart.** On start, before serving,
  `cache_reconcile.py` clears any *orphaned* dirty entry (dirty meta with no data
  to upload — the silent `Dirty:true, Size:0` data-loss state). rclone then
  re-fetches the current cloud object on the first poll instead of blocking
  change-polling or uploading an empty file.
- **Write-back health.** The refresher polls `vfs/stats` and scans the VFS cache
  each health cycle. A dirty entry that stays dirty past a grace period
  (`max(3 × writeBack, 30s)`) without progressing, or a non-zero `erroredFiles`
  count, moves write-back health to `degraded` and emits a structured, alertable
  error naming the path — in the same health state used for auth-refresh
  failures. Detection is in-band; it does not depend on external monitoring.

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
