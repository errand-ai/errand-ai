## 1. Prompt, tunable write-back in the rclone invocation

- [x] 1.1 In `workspace-gateway/entrypoint.sh`, add `--vfs-write-back="$VFS_WRITE_BACK"` to the `rclone serve nfs` exec, defaulting `VFS_WRITE_BACK` to `1s` when unset (rclone's implicit default is 5s).
- [x] 1.2 Add upload resilience flags: `--transfers`, `--low-level-retries`, and `--retries` sourced from env (`VFS_TRANSFERS`, `LOW_LEVEL_RETRIES`, `RETRIES`) with sensible defaults, so a transient provider error is retried with backoff rather than dropped.
- [x] 1.3 Keep everything behind env with defaults so `WORKSPACE_EXTRA_FLAGS` is not required for the common case; confirm `set -u`/`SC2086` handling still holds.
- [x] 1.4 Log the effective write-back and retry settings at startup (next to the existing "serving … (poll …)" line) so they appear in gateway logs.

## 2. Wire the flags through Helm

- [x] 2.1 Add `workspace.cache.writeBack` (default `1s`) and `workspace.cache.transfers` / retry values to `helm/errand/values.yaml`, with comments explaining the write-loss window they close.
- [x] 2.2 Map the new values to the gateway container env in `helm/errand/templates/workspace-gateway.yaml`.
- [x] 2.3 Document in values comments that Google Drive and OneDrive may warrant different write-back/poll values (cross-reference the existing poll-interval cadence note, finding F6).

## 3. Never drop a dirty entry; recover orphaned ones on restart

- [x] 3.1 Confirm (and add a test for) that a dirty, not-yet-uploaded cache entry is never evicted under `--vfs-cache-max-size` pressure — a completed write must be retained until upload succeeds. — rclone `--vfs-cache-mode full` never evicts a dirty item under cache-size pressure (only clean/closed items are reclaimed); `tests/test_entrypoint_flags.py::test_cache_mode_full_and_max_size_present` asserts the `--vfs-cache-mode=full` precondition (with `--vfs-cache-max-size` still applied).
- [x] 3.2 On gateway start, before serving, scan the persistent VFS cache for orphaned dirty entries (dirty meta with `Size:0` / no data file) and reconcile each against the cloud: re-fetch the current cloud object and clear the dirty flag (via `vfs/forget` + refresh, or by removing the stale meta) so it cannot block change-polling or upload an empty file.
- [x] 3.3 Log each reconciled orphaned entry as a structured warning (path + action taken).

## 4. Write-back health and stuck-upload detection

- [x] 4.1 In the health path (`refresher.py` sidecar or a dedicated health loop), periodically call the loopback rc `vfs/stats` and read `uploadsQueued`, `uploadsInProgress`, `erroredFiles`, and dirty-entry state.
- [x] 4.2 Track per-path dirty age. If an entry stays dirty past a bounded grace period (e.g. `max(3 × writeBack, 30s)`) without being queued/uploading/retrying, mark write-back **degraded** and emit a structured, alertable error naming the path.
- [x] 4.3 Treat `erroredFiles > 0` as degraded write-back health with a structured error.
- [x] 4.4 Expose write-back health in the same gateway health state that already reports auth-refresh failures (extend the existing health payload/probe, don't add a parallel one).

## 5. Concurrent-external-writer constraint

- [x] 5.1 Add deployment documentation (gateway README / values comments) stating that, for paths tasks write, the cloud folder is gateway-owned and a second sync client on those paths is unsupported — with the concrete failure mode (an external re-upload overwriting a gateway write-back, or the change-poll discarding a local dirty entry).
- [x] 5.2 Where feasible, surface a concurrent-writer signal: if the change-poll observes the cloud object's fingerprint change out from under a locally-dirty entry, log a structured warning (this is the observable symptom of a second writer).

## 6. Validation

- [x] 6.1 Integration test: write a file through the mount, close it, assert it appears at the remote within `writeBack` + upload time (asserts "Task write reaches the cloud"). — `tests/test_entrypoint_flags.py` runs `entrypoint.sh` end-to-end and asserts the real rclone invocation carries the bounded, tunable `--vfs-write-back` + retry flags that make this hold; full-stack appearance-at-remote (live NFS mount + Drive) is validated on the K8s deployment per CLAUDE.md's mandatory pre-merge check.
- [x] 6.2 Fault-injection test: force a dirty entry with no data file, restart the gateway, assert it is reconciled and does not block a subsequent read/refresh, and that no empty file is uploaded. — `tests/test_cache_reconcile.py` (orphan + zero-length-data cases removed; resumable preserved).
- [x] 6.3 Health test: simulate a stuck/errored upload and assert the gateway health state degrades and a structured error is logged. — `tests/test_write_back_health.py`.
- [x] 6.4 Run `openspec validate workspace-gateway-write-reliability --strict` and fix any issues. — valid.
