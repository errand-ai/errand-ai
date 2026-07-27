## ADDED Requirements

### Requirement: Write-back integrity — complete or failed, never partial

An upload SHALL publish the complete cached content of an entry or fail. The gateway SHALL NOT publish a partially-written object under any circumstance, including when the entry's own cache metadata is inconsistent with its data file.

After an upload reports success, the gateway SHALL verify the resulting cloud object's size against the size of the cached data that was uploaded. A mismatch SHALL be treated as an upload failure: retried per the existing retry policy and, if it persists, surfaced as degraded write-back health with a structured error naming the path. A size-verification failure SHALL NOT clear the entry's dirty flag, so the local content is retained for a subsequent attempt rather than discarded.

Length equality alone SHALL NOT be taken as evidence of a correct upload where the cached entry's metadata is known to be inconsistent (see "Metadata/data desync is detected and repaired"): the production corruption produced an object of exactly the expected byte count whose content was a mix of new and stale bytes.

#### Scenario: Partial upload is rejected, not published

- **WHEN** an upload would publish fewer bytes than the cached entry holds
- **THEN** the upload fails, the entry remains dirty with its data retained, and the gateway reports degraded write-back health naming the path

#### Scenario: Size mismatch after upload is treated as failure

- **WHEN** an upload reports success but the cloud object's size differs from the uploaded cached data's size
- **THEN** the gateway treats it as an upload failure, retains the dirty entry, retries, and on persistent failure logs a structured error naming the path

#### Scenario: Verified upload clears the entry

- **WHEN** an upload completes and the cloud object's size matches the uploaded cached data
- **THEN** the entry's dirty flag is cleared and the cached data may be evicted normally

### Requirement: Dirty entries are bounded regardless of open-handle state

A dirty cache entry SHALL NOT be exempt from write-back progress expectations or from stuck-upload detection solely because a client holds it open. NFSv3 has no `CLOSE` operation, so a task container terminated mid-mount leaves the entry permanently in-use; a close-triggered write-back delay alone therefore permits a dirty entry to remain unuploaded indefinitely (observed in production as `in use 2` sustained for over 24 hours with no upload ever queued).

The gateway SHALL bound how long an entry may remain dirty irrespective of open-handle state. Past an operator-configurable maximum dirty age, an entry that has never been queued SHALL be reported as degraded write-back health with a structured error identifying the path and the pinned-by-handle condition.

Forcing a flush of a pinned entry SHALL be opt-in and disabled by default, because a client may still be writing it and publishing a torn state is the failure this requirement exists to prevent. Reporting SHALL be the default behaviour: a stalled-but-reported write is recoverable, a torn published write may not be.

#### Scenario: Handle held open past the bound is reported

- **WHEN** a cache entry has been dirty past the configured maximum dirty age and has never been queued for upload, while still marked in-use
- **THEN** the gateway reports degraded write-back health and logs a structured error naming the path and identifying the entry as pinned by an open handle

#### Scenario: Abandoned mount does not silently strand a write

- **WHEN** a task container is terminated without unmounting after writing a file
- **THEN** the entry does not remain dirty and unreported — it is either uploaded or surfaced as degraded within the configured bound

### Requirement: Metadata/data desync is detected and repaired

The startup reconcile SHALL treat a dirty entry whose cache metadata is inconsistent with its data file as a fault, in addition to the already-covered case of a dirty entry with no data file. Specifically, a dirty entry whose metadata reports `Size: 0` and no read ranges while a non-empty data file is present is inconsistent and SHALL NOT be uploaded in that state — uploading from such an entry is what produced the production corruption.

For an inconsistent entry, the gateway SHALL prefer **repair over deletion**: the metadata SHALL be corrected to match the data file (size set to the data file's actual length, read ranges set to the full extent) so that the complete cached content is uploaded. The data file SHALL NOT be deleted to resolve an inconsistency, because it may hold the only copy of a completed write.

Repair SHALL be conditional on the gateway still being the sole writer of the path. If the entry's recorded remote fingerprint no longer matches the current cloud object, the local content is not a safe successor to the remote and the entry SHALL be quarantined — moved aside within the persistent cache and reported with a structured error — rather than repaired and uploaded. Quarantined content SHALL be retained for manual recovery, and its location SHALL be documented in the gateway operational runbook.

Reconcile actions SHALL be performed only while `rclone serve` is not running, so repair never races a live cache.

#### Scenario: Inconsistent entry is repaired and uploaded in full

- **WHEN** startup finds a dirty entry with `Size: 0` metadata, a non-empty data file, and a remote fingerprint still matching the cloud object
- **THEN** the metadata is repaired to match the data file, the entry remains dirty, and the complete cached content is uploaded

#### Scenario: Inconsistent entry with a changed remote is quarantined

- **WHEN** startup finds an inconsistent dirty entry whose recorded remote fingerprint no longer matches the current cloud object
- **THEN** the entry is quarantined rather than uploaded, its content is retained for manual recovery, and a structured error names the path and the fingerprint mismatch

#### Scenario: Reconcile never deletes the only copy of a write

- **WHEN** a dirty entry's metadata is inconsistent but its data file holds content
- **THEN** the data file is preserved — repaired or quarantined — and never removed to clear the inconsistency

### Requirement: Gateway operational runbook

The repository SHALL contain an operational runbook for the workspace gateway covering, at minimum: the safe procedure for taking the gateway out of service, how to detect a stalled write-back, and how to recover content from a stalled or quarantined cache entry.

The runbook SHALL state that the gateway deployment is managed by a continuous-delivery controller with self-heal enabled, so an unsuspended replica scale-down is reverted automatically and the resulting restart flushes dirty cache entries. It SHALL document suspending automated sync before any maintenance that stops the gateway, and SHALL require taking a backup of both the cache-side and cloud-side copies of any dirty path before a reconcile or restart is attempted.

#### Scenario: Operator takes the gateway down safely

- **WHEN** an operator needs to stop the gateway to act on its cache
- **THEN** the runbook directs them to suspend automated sync first, confirm no task containers are mounting the export, and back up both copies of any dirty path before proceeding

#### Scenario: Operator recovers a stalled write

- **WHEN** the gateway reports degraded write-back health naming a path
- **THEN** the runbook describes how to retrieve that path's cached content and reconcile it against the cloud copy without losing either version

## MODIFIED Requirements

### Requirement: Write-back upload with persistent cache

The gateway SHALL run with `--vfs-cache-mode full` and a cache directory on persistent storage. File writes through the mount SHALL be uploaded to the cloud provider promptly after file close, within a bounded, operator-configurable write-back delay. The write-back delay (`--vfs-write-back`) SHALL be set explicitly (default short, e.g. `1s`) rather than relying on rclone's implicit default, and SHALL be exposed as a tunable so it can be validated per provider. Upload failures SHALL be retried with backoff (`--retries` / `--low-level-retries`) so a transient provider error keeps the write in a retrying state rather than dropping it.

A completed write SHALL NOT be lost between `close()` and upload: the VFS cache SHALL retain a dirty (not-yet-uploaded) entry's data until its upload succeeds, and SHALL NOT evict a dirty entry under cache-size pressure.

A dirty cache entry SHALL always be progressing toward upload — it SHALL be queued, uploading, or retrying-after-a-logged-error. A cache entry that is marked dirty while neither queued, uploading, nor retrying is a fault and SHALL be detected and surfaced, never left silent (see "Write-back health and stuck-upload detection"). This fault has been observed in production in two distinct forms, both of which SHALL be covered: `Dirty:true, Size:0` with `uploadsQueued:0` and **no data file**, and `Dirty:true, Size:0` with `uploadsQueued:0` and a **non-empty data file present** (see "Metadata/data desync is detected and repaired"). A dirty entry SHALL NOT be presumed to be a resumable upload merely because a data file exists.

Pending uploads SHALL survive a gateway restart: on start, the gateway SHALL resume uploading any writes queued in the persistent cache, and SHALL reconcile any orphaned dirty entry (a dirty cache item with no data to upload) against the cloud rather than leaving it to block change-polling or upload an empty file. Resuming SHALL NOT include uploading from an entry whose metadata is inconsistent with its data; such entries SHALL be repaired or quarantined before any upload is attempted.

#### Scenario: Task write reaches the cloud

- **WHEN** a task writes a file to the mounted workspace and closes it
- **THEN** the file appears in the cloud folder with the exact name and location the task used, within the configured write-back delay plus upload time

#### Scenario: Write is not dropped between close and upload

- **WHEN** a task has written and closed a file but the gateway has not yet completed the upload
- **THEN** the file's cached data is retained until the upload succeeds, even under `--vfs-cache-max-size` pressure — a dirty entry is never evicted or dropped

#### Scenario: Gateway restart with pending uploads

- **WHEN** the gateway process terminates while uploads are queued in the VFS cache
- **THEN** after restart the queued uploads complete without data loss

#### Scenario: Orphaned dirty entry recovered on restart

- **WHEN** the persistent cache contains a dirty entry that has no data file to upload
- **THEN** on startup the gateway reconciles it against the cloud (re-fetching the current cloud object and clearing the dirty flag), so the entry does not block change-polling and no empty file is uploaded

#### Scenario: Dirty entry with data is not assumed resumable

- **WHEN** the persistent cache contains a dirty entry with a non-empty data file whose metadata reports `Size: 0`
- **THEN** the gateway does not treat it as a resumable upload and does not upload it in that state — it is repaired or quarantined first

### Requirement: Write-back health and stuck-upload detection

The gateway SHALL monitor its own VFS write-back queue via the loopback rclone rc API (`vfs/stats`, already exposed to the refresher) and SHALL reflect write-back health in the same health state and structured, alertable logs already used for auth-refresh failures. Detection SHALL be in-band and SHALL NOT depend on any external monitoring system, so that silent data loss is not possible.

A stuck upload — a dirty cache entry that is not progressing (not queued, not uploading, not retrying) beyond a bounded grace period derived from the write-back delay, or a non-zero `erroredFiles` count — SHALL move the gateway to a degraded write-back health state and emit a structured error identifying the affected path.

The monitor SHALL be able to observe what it monitors. The component performing detection SHALL have read access to the persistent VFS cache metadata in the deployed configuration; a filesystem-permission or identity mismatch between the process writing the cache and the process scanning it SHALL be treated as a deployment defect. The gateway SHALL verify this access at startup and log the outcome explicitly, so a configuration in which detection cannot run is loud immediately rather than silent until a fault occurs.

A failure to scan the cache SHALL itself be a degraded, alertable condition, reported with the underlying error. An unreadable cache SHALL NOT be reported as healthy and SHALL NOT be indistinguishable from an absence of faults — otherwise the monitor's own failure mode reproduces the silent data loss it exists to prevent.

#### Scenario: Stuck upload is surfaced, not silent

- **WHEN** a file remains dirty in the VFS cache past the grace period without being queued, uploading, or retrying
- **THEN** the gateway health state reports write-back degraded and logs a structured error naming the file, rather than the write silently never reaching the cloud

#### Scenario: Errored upload is alertable

- **WHEN** `vfs/stats` reports `erroredFiles > 0`
- **THEN** the gateway reflects the error in health state and structured logs with enough detail to identify the affected file(s)

#### Scenario: Monitor verifies its own visibility at startup

- **WHEN** the gateway starts
- **THEN** the monitoring component attempts a cache scan and logs the outcome, so a deployment in which it cannot read the cache is reported immediately

#### Scenario: Unreadable cache is degraded, not healthy

- **WHEN** the monitoring component cannot read the persistent VFS cache metadata (for example a permission error)
- **THEN** write-back health is reported degraded with the underlying error, and is never reported as healthy or as an absence of dirty entries
