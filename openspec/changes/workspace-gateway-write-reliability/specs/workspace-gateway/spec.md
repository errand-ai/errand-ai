## MODIFIED Requirements

### Requirement: Write-back upload with persistent cache

The gateway SHALL run with `--vfs-cache-mode full` and a cache directory on persistent storage. File writes through the mount SHALL be uploaded to the cloud provider promptly after file close, within a bounded, operator-configurable write-back delay. The write-back delay (`--vfs-write-back`) SHALL be set explicitly (default short, e.g. `1s`) rather than relying on rclone's implicit default, and SHALL be exposed as a tunable so it can be validated per provider. Upload failures SHALL be retried with backoff (`--retries` / `--low-level-retries`) so a transient provider error keeps the write in a retrying state rather than dropping it.

A completed write SHALL NOT be lost between `close()` and upload: the VFS cache SHALL retain a dirty (not-yet-uploaded) entry's data until its upload succeeds, and SHALL NOT evict a dirty entry under cache-size pressure.

A dirty cache entry SHALL always be progressing toward upload — it SHALL be queued, uploading, or retrying-after-a-logged-error. A cache entry that is marked dirty while neither queued, uploading, nor retrying (observed in production as `Dirty:true, Size:0` with `uploadsQueued:0` and no data file) is a fault and SHALL be detected and surfaced, never left silent (see "Write-back health and stuck-upload detection").

Pending uploads SHALL survive a gateway restart: on start, the gateway SHALL resume uploading any writes queued in the persistent cache, and SHALL reconcile any orphaned dirty entry (a dirty cache item with no data to upload) against the cloud rather than leaving it to block change-polling or upload an empty file.

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

## ADDED Requirements

### Requirement: Write-back health and stuck-upload detection

The gateway SHALL monitor its own VFS write-back queue via the loopback rclone rc API (`vfs/stats`, already exposed to the refresher) and SHALL reflect write-back health in the same health state and structured, alertable logs already used for auth-refresh failures. Detection SHALL be in-band and SHALL NOT depend on any external monitoring system, so that silent data loss is not possible.

A stuck upload — a dirty cache entry that is not progressing (not queued, not uploading, not retrying) beyond a bounded grace period derived from the write-back delay, or a non-zero `erroredFiles` count — SHALL move the gateway to a degraded write-back health state and emit a structured error identifying the affected path.

#### Scenario: Stuck upload is surfaced, not silent

- **WHEN** a file remains dirty in the VFS cache past the grace period without being queued, uploading, or retrying
- **THEN** the gateway health state reports write-back degraded and logs a structured error naming the file, rather than the write silently never reaching the cloud

#### Scenario: Errored upload is alertable

- **WHEN** `vfs/stats` reports `erroredFiles > 0`
- **THEN** the gateway reflects the error in health state and structured logs with enough detail to identify the affected file(s)

### Requirement: Gateway is the sole writer of task-written paths

For any path that tasks write through the mount, the cloud folder SHALL be treated as owned by the gateway. A second sync client writing the same paths concurrently (for example a human's native Google Drive or OneDrive desktop client syncing the same folder) is unsupported: such concurrent external writes can overwrite a gateway write-back or cause the VFS to discard a local dirty entry on the next change-poll. Deployment documentation SHALL state this constraint and direct operators to scope the cloud folder to gateway-owned content or exclude task-written subpaths from other sync clients. Where feasible, the gateway SHALL log a structured warning when a locally-dirty object's remote fingerprint changes underneath it, since that is the observable symptom of a second writer.

#### Scenario: Concurrent external writer overwrites a task write

- **WHEN** a native desktop sync client re-uploads its own older copy of a file that a task has just written through the mount
- **THEN** this is a known, documented failure mode; the deployment guidance directs operators to prevent a second writer on task-written paths, and the gateway logs a structured warning identifying the contended path rather than silently reconciling in the external writer's favour
