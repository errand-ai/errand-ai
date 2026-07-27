# Workspace gateway — operational runbook

Operating the shared-workspace gateway (`rclone serve nfs` + refresher sidecar)
and its VFS cache PVC. Written after the 2026-07-26 incident, in which a routine
`kubectl scale` triggered a restart that published a corrupted file over a user's
Google Drive document.

**The one-line version:** the cache PVC can hold the only copy of completed work.
Back up both sides before you touch it, and suspend ArgoCD before you stop
anything.

---

## 1. Before you do anything: what can go wrong

The gateway's VFS cache holds writes that have not yet reached the cloud. A
"dirty" cache entry is a completed local write awaiting upload. Two failure
shapes have been seen in production:

| Shape | Metadata | Data file | Consequence |
|---|---|---|---|
| **Orphaned** | `Dirty: true, Size: 0, Rs: null` | **absent** | Nothing to upload; blocks change-polling, or uploads an empty file over the good cloud copy |
| **Desynced** | `Dirty: true, Size: 0, Rs: null` | **present, non-empty** | Uploading from this state publishes a **partial write** — new content over the head of a stale buffer, old tail retained |

The startup reconcile handles both (§6). What it cannot do is undo an upload that
already happened, which is why the backup step in §3 is not optional.

---

## 2. Taking the gateway out of service

> **Suspend ArgoCD auto-sync FIRST.** The gateway Deployment is ArgoCD-managed
> with self-heal. A bare `kubectl scale --replicas=0` is reverted within seconds,
> and the resulting restart flushes dirty cache entries — publishing whatever is
> in the cache, including a desynced entry. **This is exactly how the 2026-07-26
> corruption was triggered.**

```bash
# 1. Suspend automated sync (do this BEFORE scaling anything)
kubectl -n argocd patch application errand --type merge \
  -p '{"spec":{"syncPolicy":{"automated":null}}}'

# 2. Confirm it took effect — syncPolicy.automated must be gone
kubectl -n argocd get application errand -o jsonpath='{.spec.syncPolicy}'; echo

# 3. Confirm no task-runner pods are mounting the export (§2.1)

# 4. Back up both sides of every dirty path (§3) — MANDATORY

# 5. Only now scale down
kubectl -n errand scale deploy/errand-workspace-gateway --replicas=0
kubectl -n errand rollout status deploy/errand-workspace-gateway --timeout=120s
```

Restore afterwards:

```bash
kubectl -n errand scale deploy/errand-workspace-gateway --replicas=1
kubectl -n argocd patch application errand --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
```

### 2.1 Confirm no task-runner pods are mounting the export

Stopping the gateway while a task holds the mount gives that task stale NFS
handles (`ESTALE`), and a task writing at that moment can leave a half-written
entry in the cache.

```bash
# Any running task-runner pods at all?
kubectl -n errand get pods -l app.kubernetes.io/component=task-runner

# Which of them actually mount the shared workspace?
kubectl -n errand get pods -l app.kubernetes.io/component=task-runner \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*].persistentVolumeClaim.claimName}{"\n"}{end}' \
  | grep errand-workspace

# The gateway's own view — "in use N" on the rclone log lines
kubectl -n errand logs deploy/errand-workspace-gateway -c rclone --tail=20 | grep -o 'in use [0-9]*' | tail -5
```

Wait for them to finish, or pause task processing, before proceeding. Note that
`in use N` can stay non-zero **after** the pods are gone: NFSv3 has no `CLOSE`,
so a pod torn down mid-mount leaves the handle leaked forever. That is a stalled
write, not an active one — see §5.3.

---

## 3. Mandatory: back up BOTH sides before a reconcile or restart

Before any action that stops or restarts the gateway, capture the cache-side and
cloud-side copies of every dirty path. They differ — that is the entire point.

```bash
GW=deploy/errand-workspace-gateway
BACKUP=~/gateway-backup-$(date +%Y%m%d-%H%M%S); mkdir -p "$BACKUP"

# 1. List dirty entries (metadata side)
kubectl -n errand exec $GW -c rclone -- \
  sh -c 'grep -rl "\"Dirty\":true" /cache/vfsMeta || true'

# For each dirty path P reported above (e.g. gdrive{a1b2}/workflow/Notes.md):
P='gdrive{a1b2}/workflow/Notes.md'
REL="${P#*/}"                     # path within the served folder

# 2. Cache side — size, checksum, and the content itself
kubectl -n errand exec $GW -c rclone -- sh -c "cat '/cache/vfsMeta/$P'"
kubectl -n errand exec $GW -c rclone -- sh -c "wc -c '/cache/vfs/$P'; md5sum '/cache/vfs/$P'"
kubectl -n errand exec $GW -c rclone -- sh -c "cat '/cache/vfs/$P'" > "$BACKUP/cache-$(basename "$REL")"

# 3. Cloud side — size, checksum, and the content itself
kubectl -n errand exec $GW -c rclone -- rclone lsjson --stat --hash "gdrive:$REL"
kubectl -n errand exec $GW -c rclone -- rclone cat "gdrive:$REL" > "$BACKUP/cloud-$(basename "$REL")"

# 4. Verify the backups are non-empty and record their checksums
ls -l "$BACKUP"; md5sum "$BACKUP"/*
```

Do not proceed until both files exist locally and their sizes look sane. If the
two differ in length, the cache copy is the newer local work and the cloud copy
is what a bad flush would overwrite — keep both.

> Substitute the remote name and served folder for your deployment
> (`workspace.remote` / `workspace.folder` in the Helm values).

---

## 4. Detecting a stalled write-back

### 4.1 Health state (the primary signal)

The refresher reports `write_back_state` to the errand server every ~30s.
`degraded` always names a reason and, where applicable, a path:

| Reason | Meaning | Action |
|---|---|---|
| `cache_scan_failed` | The refresher **cannot read the cache** — detection is blind | Deployment defect. Check the uid of both containers (§4.4) |
| `orphaned_dirty_entry` | Dirty, but no data file exists to upload | Reconcile on next restart (§6) |
| `dirty_entry_not_progressing` | Dirty past the grace period with an idle upload queue | §5 |
| `dirty_entry_pinned_by_handle` | Dirty past `maxDirtyAgeSeconds`, never queued — a leaked NFS handle | §5.3 |
| `dirty_entry_overdue` | Dirty past the absolute backstop despite a busy queue | §5 |
| `upload_size_mismatch` | The published object's size ≠ the cached data uploaded | §5.4 |
| `errored_uploads` | `vfs/stats` reports `erroredFiles > 0` | Check the rclone logs for the provider error |

### 4.2 rclone's own counters

```bash
kubectl -n errand exec deploy/errand-workspace-gateway -c rclone -- \
  rclone rc --rc-addr=127.0.0.1:5572 --rc-no-auth vfs/stats
```

**`uploadsQueued: 0, erroredFiles: 0` does not mean healthy.** That was the exact
reading throughout the 24-hour stall — an entry that is never *queued* is
invisible to these counters. Always cross-check the dirty-entry scan below.

### 4.3 Scan the cache directly (ground truth)

```bash
kubectl -n errand exec deploy/errand-workspace-gateway -c rclone -- \
  sh -c 'grep -rl "\"Dirty\":true" /cache/vfsMeta | while read m; do
           p=${m#/cache/vfsMeta/}
           printf "%s\n  meta: %s\n  data: %s\n" "$p" "$(cat "$m")" "$(wc -c < "/cache/vfs/$p" 2>/dev/null || echo MISSING)"
         done'
```

Compare `Size` in the metadata against the data file's byte count. If the
metadata says `Size: 0` / `Rs: null` while the data file is non-empty, that is
the **desynced** fault — do not restart the gateway until you have backups (§3).

### 4.4 Confirm detection is actually running

The single check that would have caught the 2026-07-26 incident on day one:

```bash
kubectl -n errand logs deploy/errand-workspace-gateway -c refresher | grep cache_scan_selftest
```

`cache_scan_selftest_ok` means the refresher can read the cache. If you see
`cache_scan_selftest_failed`, stuck-entry detection **cannot run at all** and the
gateway is silently unmonitored. Verify both containers share a uid:

```bash
kubectl -n errand exec deploy/errand-workspace-gateway -c rclone -- id
kubectl -n errand exec deploy/errand-workspace-gateway -c refresher -- id
kubectl -n errand exec deploy/errand-workspace-gateway -c rclone -- ls -ld /cache/vfs /cache/vfsMeta
```

rclone creates those directories mode `0700`, so a differing uid makes them
unreadable. Fix `workspace.runAsUser` in the Helm values — a shared *group* does
not help, because `0700` grants the group nothing.

---

## 5. Recovering a stalled write

Always §3 first. Then, by reason:

### 5.1 Orphaned entry (no data file)

Nothing to recover — the write's data was lost before it was cached. Restarting
the gateway runs the reconcile, which clears the stale metadata so the next poll
re-fetches the cloud object. Tell the task owner the write did not land.

### 5.2 Desynced entry (data present, metadata says empty)

The cache holds the only copy of the work. **Do not restart before backing up.**
The reconcile repairs this automatically on the next start (§6), but recover the
content by hand first so a bad outcome is survivable:

```bash
kubectl -n errand exec $GW -c rclone -- sh -c "cat '/cache/vfs/$P'" > recovered.md
```

Then reconcile the recovered content against the cloud copy from §3 by hand
(they may each contain edits the other lacks) and write the merged result back
through the mount, or directly to Drive.

### 5.3 Entry pinned by a leaked handle

`dirty_entry_pinned_by_handle` means the entry has been dirty past
`maxDirtyAgeSeconds` and was never queued for upload. `--vfs-write-back` is
close-triggered and NFSv3 has no `CLOSE`, so a task container torn down mid-mount
pins the entry forever.

The gateway **reports** this rather than force-flushing it, deliberately: the
file may be half-written, and publishing a torn object is worse than a stalled
one. `workspace.writeBackHealth.forceFlushPinned` exists but rclone's rc API
offers no safe way to flush a dirty, never-queued item (`vfs/queue-set-expiry`
only reorders items already queued), so enabling it logs
`force_flush_unavailable` and changes nothing. Recover by hand:

1. Back up both sides (§3).
2. Confirm no task is still writing the path (§2.1).
3. Copy the cached content out, verify it is complete and well-formed.
4. Write it back through the mount from a fresh client, or upload it directly.

### 5.4 Upload size mismatch

`upload_size_mismatch` means rclone reported a successful upload but the
published object's size differs from the cached data that was uploaded. The local
copy is retained in the cache PVC. Back up both sides (§3), compare them, and
re-publish the correct content by hand. Do not clear the cache until you have.

---

## 6. The startup reconcile and quarantine

`cache_reconcile.py` runs from the gateway entrypoint **before** `rclone serve`
starts, so it never races a live cache. Per dirty entry:

- **orphaned** (no data file) → stale metadata cleared;
- **desynced** *and* the recorded remote fingerprint still matches the cloud
  object → metadata **repaired** (`Size` set to the data file's real length, `Rs`
  to the full extent), entry left dirty so the complete content uploads;
- **desynced** *and* no cloud object exists *and* the entry records no
  fingerprint (a brand-new file that never uploaded) → **repaired**: there is
  nothing to overwrite, so stranding the work would buy no safety;
- **desynced** otherwise → **quarantined**, with the reason distinguishing what
  happened: `fingerprint_mismatch` (the cloud object moved under the entry — a
  second writer), `remote_deleted` (it existed when cached and does not now), or
  `remote_unverifiable` (the remote could not be listed at all).

Quarantine never deletes anything. Both the data file and its metadata move to:

```
/cache/quarantine/vfs/<path>        # the content
/cache/quarantine/vfsMeta/<path>    # the metadata as it was
/cache/quarantine/manifest.jsonl    # one JSON line per quarantine: path, reason, sizes, timestamp
```

A repeat quarantine of the same path appends `.1`, `.2`, … rather than
overwriting the earlier rescue copy.

```bash
# What has been quarantined, and why
kubectl -n errand exec $GW -c rclone -- cat /cache/quarantine/manifest.jsonl

# Pull a quarantined file out
kubectl -n errand exec $GW -c rclone -- sh -c "cat '/cache/quarantine/vfs/$P'" > recovered.md
```

Reconcile actions are logged as structured JSON:
`orphaned_dirty_entry_reconciled`, `desynced_dirty_entry_repaired`,
`desynced_dirty_entry_quarantined`, and the summary `cache_reconcile_complete`.

```bash
kubectl -n errand logs deploy/errand-workspace-gateway -c rclone | grep -E 'reconcil|quarantin|repaired'
```

Quarantined files are **not** cleaned up automatically. Once you have recovered
the content, delete them by hand to reclaim PVC space.

---

## 7. Known hazard: a second writer on the same folder

The `workspace-gateway` specification requires the gateway to be the **sole
writer** of task-written paths. A second sync client on the same cloud folder is
**unsupported** and can overwrite a gateway write-back, or move the remote object
underneath a dirty cache entry.

> **A Google Drive desktop client is currently syncing the same `workflow/`
> folder the gateway serves.** This is a standing hazard, not a hypothetical: it
> is why the reconcile has a fingerprint guard at all, and a fingerprint change
> under a dirty entry logs `concurrent_writer_detected`.

Mitigation is to exclude the gateway's folder from the desktop client so rclone
is the only writer. Until that is done, expect occasional `fingerprint_mismatch`
quarantines and treat them as real conflicts requiring a manual merge.

---

## 8. Startup token requirement

The gateway refuses to start without a usable access token for its remote in the
writable rclone config, exiting with `FATAL: no usable access token`. This is
deliberate: rclone would otherwise fall through to an interactive OAuth flow
whose redirect listener holds `127.0.0.1:53682` for the life of the process,
making every refresher `rclone rc config/update` fail with
`bind: address already in use` — token rotation would silently never happen.

The `init-token` init container seeds a fresh token before rclone starts. If the
gateway is in `CrashLoopBackOff` with that message, check the init container:

```bash
kubectl -n errand logs deploy/errand-workspace-gateway -c init-token
```

Verify nothing is listening on the OAuth port in a healthy gateway:

```bash
kubectl -n errand exec deploy/errand-workspace-gateway -c rclone -- \
  sh -c 'netstat -ltn 2>/dev/null | grep 53682 || echo "53682 free (expected)"'
```
