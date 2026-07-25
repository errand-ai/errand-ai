## Why

The `workspace-gateway` capability promises, under "Write-back upload with persistent cache", that a task's file writes reach the cloud. In practice writes through `/shared` have been observed to silently fail to persist, causing data loss.

A task appended entries to `/shared/BlogsToProcess.md` with an ordinary `cat > file` (write + close). The new content was visible to later reads through the mount, but **never reached Google Drive**. Inspecting the gateway VFS cache found an orphaned dirty entry:

```
"Dirty": true, "Size": 0, "Rs": null        (no data file on disk)
vfs/stats: uploadsQueued: 0, uploadsInProgress: 0, erroredFiles: 0
```

rclone believed there was an unsaved change but had neither the data nor a queued upload — the write was simply lost, silently. This violates the "Task write reaches the cloud" scenario.

Three gaps make this possible today:

1. The gateway runs `--vfs-cache-mode=full` with rclone's **default `--vfs-write-back` (5s)** and no explicit retry tuning, leaving a window in which a completed write can be lost before it uploads (`workspace-gateway/entrypoint.sh` sets no write-back flag).
2. There is **no detection or alerting** when a dirty cache entry becomes stuck (dirty but not queued/uploading/retrying), so the failure is invisible.
3. When a **second writer** (e.g. a human's native Drive desktop client syncing the same folder) touches the same file, the change-poll can discard the gateway's local dirty write with no signal.

## What Changes

- Set an explicit, operator-tunable `--vfs-write-back` (short, e.g. `1s`) so completed writes upload promptly, and add upload retry/backoff flags to the `rclone serve nfs` invocation.
- Require a dirty cache entry to *always* be progressing toward upload (queued, uploading, or retrying-after-logged-error). A dirty-but-idle entry is a fault that MUST be detected.
- Add **write-back health**: the gateway polls its own `vfs/stats` (rc API, already on loopback) and reflects stuck/errored uploads in the same health state + structured, alertable logs already used for auth-refresh failures — so silent loss becomes impossible.
- On restart, reconcile any **orphaned dirty entry** (dirty meta with no data) against the cloud rather than leaving it to block change-polling or risk uploading an empty file.
- Document the **concurrent-external-writer** constraint: task-written paths are gateway-owned; a second sync client on the same paths is unsupported and its risk is called out for operators.
- Expose the new flags via Helm values so they are tunable per provider (Google Drive and OneDrive cadences differ).

## Capabilities

### Modified Capabilities

- `workspace-gateway`: strengthen "Write-back upload with persistent cache" (prompt write-back, no-drop-while-dirty, orphaned-entry recovery); add "Write-back health and stuck-upload detection" and "Gateway is the sole writer of task-written paths".

## Impact

- **Gateway image** — `workspace-gateway/entrypoint.sh`: add `--vfs-write-back` and retry flags to `rclone serve nfs`, sourced from env.
- **Helm** — `helm/errand/templates/workspace-gateway.yaml`, `values.yaml`: new `workspace.cache.writeBack` (+ retry) values wired to gateway env; defaults tuned for Google Drive.
- **Health/refresher** — `workspace-gateway/refresher.py` (or the health probe): poll `vfs/stats` and surface write-back health; degrade + log on stuck/errored uploads.
- **Docs** — deployment notes: the cloud folder must not be concurrently written by another sync client for task-written paths.
- No task-runner, API, or mount-contract changes. The behaviour change is limited to *how reliably writes upload* and *how failures surface*.

## Non-goals

- Replacing the Drive/OneDrive-backed rclone mount with a native shared volume (PVC). That would sidestep these cloud quirks entirely but changes the product's "files live in the user's Drive" premise; it is a larger, separate decision recorded in `design.md` under Alternatives.
- Automatically merging concurrent edits from an external sync client. The gateway detects and surfaces the conflict; it does not attempt three-way merge.
