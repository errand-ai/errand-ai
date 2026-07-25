## Context

The workspace gateway exposes a Google Drive / OneDrive folder over NFS to task containers using `rclone serve nfs … --vfs-cache-mode=full`. Tasks read and write files under `/shared`. The write path is: task `write()`+`close()` → rclone VFS cache (marks the item dirty) → write-back uploads the object to the cloud provider. This design targets the reliability of that last hop, which has produced silent data loss.

## Observed failure (what prompted this)

A task appended ~6 entries to `/shared/BlogsToProcess.md` via `cat /tmp/queue.md > /shared/BlogsToProcess.md`. Reads through the mount showed the new content, but Google Drive kept the pre-write version. The gateway cache held:

- `vfsMeta/.../workflow/BlogsToProcess.md`: `{"Dirty": true, "Size": 0, "Rs": null, "Fingerprint": "<old version>"}`
- no corresponding `vfs/.../workflow/BlogsToProcess.md` data file
- `vfs/stats`: `uploadsQueued: 0, uploadsInProgress: 0, erroredFiles: 0`

So rclone recorded a dirty change, lost the data backing it, and never queued an upload — a terminal "dirty but idle" state. Nothing surfaced the fault; the task reported success. A parallel factor: the cloud object's modtime had advanced to a value the gateway did not write, consistent with a **second writer** (a native desktop Drive client syncing the same folder) re-uploading its own copy and the change-poll then discarding the local dirty entry.

## Goals

1. Shrink and bound the window between a completed write and its upload.
2. Make "dirty but idle / errored" impossible to reach silently — detect and alert.
3. Recover cleanly from an orphaned dirty entry on restart instead of letting it fester or upload an empty file.
4. Be explicit that a second concurrent writer on task-written paths is unsupported.

## Decisions

### Explicit short `--vfs-write-back`

rclone defaults `--vfs-write-back` to 5s (delay after last modification before uploading). The gateway sets it implicitly today. We set it explicitly and short (default `1s`) and make it a Helm value. This narrows the loss window and documents intent. We do not use `0s`: for large or streaming writes an immediate write-back per change is wasteful; `1s` uploads promptly after `close()` for the small-file, write-then-close pattern tasks use, while remaining tunable.

### A dirty entry must always be progressing

We make it a spec invariant that a dirty cache entry is always queued, uploading, or retrying-after-logged-error. This turns the observed terminal state into a defined fault the gateway must detect (via `vfs/stats` + dirty-age tracking) rather than an unspecified edge case. Retry/backoff flags (`--retries`, `--low-level-retries`) ensure transient provider errors keep the entry in a *retrying* state instead of dropping it.

### Health, not external monitoring

Detection lives in the gateway itself (the refresher sidecar already talks to the loopback rc API and already owns health for auth-refresh failures). Reusing that path means write-back faults show up in the same health signal and alerting operators already have, and cannot be silently missed if external monitoring is absent. We avoid a second, parallel health mechanism.

### Orphaned-entry recovery on restart

The existing requirement says pending uploads resume on restart. We extend it: an orphaned dirty entry (dirty, no data) is *not* a resumable upload — there is nothing to send. On start the gateway reconciles it against the cloud (re-fetch current object, clear dirty) so it neither blocks change-polling nor risks an empty-file upload. This is the same operation used manually to clear the stuck entry during the incident.

### Concurrent external writer is a documented constraint, not an auto-merge

The gateway cannot safely arbitrate two independent writers of the same cloud object (the native sync client has no notion of the gateway's in-flight dirty state, and vice-versa). Rather than pretend to reconcile, we require deployments to keep task-written paths gateway-owned and document the failure mode, and — where cheap — log a structured warning when a locally-dirty object's remote fingerprint changes underneath it (the observable symptom of a second writer).

## Alternatives considered

- **Drop Drive/OneDrive; back `/shared` with a native RWX volume (PVC).** Eliminates VFS-cache write-back, renames-as-new-object, and concurrent-writer conflicts in one move — the most robust option. Rejected here because it removes the product premise that shared files live in the user's own cloud drive (human-visible/editable). Recorded as the fallback if write reliability remains unacceptable after this tuning. Out of scope for this change.
- **`--vfs-cache-mode writes` instead of `full`.** Doesn't address the write-back timing or the stuck-dirty detection; `full` is required for the read-side behaviour elsewhere in the capability. No change.
- **Rely on external alerting for stuck uploads.** Rejected: the failure is silent to the task and must be caught in-band; external monitoring may be absent in some deployments.

## Risks

- A very short write-back could increase provider API calls under bursty writes; mitigated by keeping it tunable and defaulting to `1s`, not `0s`.
- Dirty-age thresholds that are too tight could flap health under normal upload latency; the grace period is derived from `writeBack` and floored (e.g. `max(3×writeBack, 30s)`).
