# workspace-gateway Specification

## Purpose
TBD - created by archiving change shared-cloud-workspace. Update Purpose after archive.
## Requirements
### Requirement: rclone NFS gateway serves a designated cloud folder

The workspace gateway SHALL run `rclone serve nfs` against a single configured cloud folder on either Google Drive or OneDrive, exposing it over NFSv3 for task containers to mount. The cloud folder SHALL be the source of truth: the gateway SHALL keep no canonical local copy, only a VFS cache. The rclone remote type (`drive` or `onedrive`) SHALL be the only provider-specific configuration; all other gateway behavior SHALL be identical for both providers.

#### Scenario: Google Drive workspace

- **WHEN** the gateway is configured with provider `google_drive` and folder `Errand`
- **THEN** task containers mounting the export see the live contents of the `Errand` folder in the user's Google Drive

#### Scenario: OneDrive workspace

- **WHEN** the gateway is configured with provider `onedrive` and folder `Errand`
- **THEN** task containers mounting the export see the live contents of the `Errand` folder in the user's OneDrive, served by the same gateway component with only the rclone remote differing

### Requirement: Change polling for live human edits

The gateway SHALL enable rclone change notification polling (`--poll-interval`, default 15s) so that edits made directly in Google Drive or OneDrive (web UI or native sync client) while a task is running become visible through the mount without gateway restart. The *effective* change-detection cadence may exceed the configured `--poll-interval` (the spike observed ~60s on Google Drive despite `--poll-interval 15s`, finding F6); the freshness window SHALL be treated as approximately the effective cadence, and the configured interval SHALL be tuned/validated against the live provider rather than assumed.

#### Scenario: Human edit visible to running task

- **WHEN** a human modifies a file in the cloud folder via the provider's web UI while a task is running
- **THEN** a subsequent read of that file through the task's `/shared` mount returns the updated content within approximately the effective poll cadence

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

### Requirement: Write-back integrity — complete or failed, never partial

An upload SHALL publish the complete cached content of an entry or fail. The gateway SHALL NOT publish a partially-written object under any circumstance, including when the entry's own cache metadata is inconsistent with its data file.

After an upload reports success, the gateway SHALL verify the resulting cloud object's size against the size of the cached data that was uploaded. A mismatch SHALL be treated as a failed publish: surfaced as degraded write-back health with a structured error naming the path, and held in that state until the path verifies clean, so a single bad publish cannot pass between two health cycles unnoticed. A size-verification failure SHALL NOT discard the cached data, so the local content remains recoverable.

The existing retry policy (`--retries` / `--low-level-retries`) covers uploads that *fail*; an upload that reports success while publishing a wrong-sized object is outside it, and the gateway SHALL NOT attempt to re-drive such an upload by writing to the cloud object outside the VFS — doing so would make the gateway a second writer of a path it is mid-write on. Detection and reporting are the required behaviour; recovery is an operator procedure (see "Gateway operational runbook").

A cached length observed only once while a write is still in progress SHALL NOT be used as the comparison basis, since a partial length would report a mismatch against a correct upload.

Length equality alone SHALL NOT be taken as evidence of a correct upload where the cached entry's metadata is known to be inconsistent (see "Metadata/data desync is detected and repaired"): the production corruption produced an object of exactly the expected byte count whose content was a mix of new and stale bytes.

#### Scenario: Partial upload is rejected, not published

- **WHEN** an upload would publish fewer bytes than the cached entry holds
- **THEN** the upload fails, the entry remains dirty with its data retained, and the gateway reports degraded write-back health naming the path

#### Scenario: Size mismatch after upload is treated as failure

- **WHEN** an upload reports success but the cloud object's size differs from the uploaded cached data's size
- **THEN** the gateway reports degraded write-back health with a structured error naming the path, retains the cached data, and stays degraded until that path verifies clean

#### Scenario: A write still in progress is not falsely reported

- **WHEN** the cached data's length has been observed only once, while the client is still writing it
- **THEN** the gateway does not compare it against the published object, and records the upload as unverified rather than mismatched

#### Scenario: Verified upload clears the entry

- **WHEN** an upload completes and the cloud object's size matches the uploaded cached data
- **THEN** the entry's dirty flag is cleared and the cached data may be evicted normally

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

### Requirement: Google-native files are excluded

The gateway SHALL be configured with `--drive-skip-gdocs` (or equivalent) so Google-native files (Docs, Sheets, Slides) are not exposed through the mount. Native-document workflows remain the responsibility of the `gws` CLI.

#### Scenario: Native Doc not exposed

- **WHEN** the cloud folder contains a Google Doc
- **THEN** the mount does not present it as a file, and no export/import round-trip is attempted

### Requirement: Token refresher keeps the gateway authenticated

A refresher process (sidecar) SHALL fetch a fresh cloud access token from the errand server on gateway start and periodically before token expiry (given 60-minute provider TTLs, at most every ~50 minutes), and SHALL inject it into the running rclone instance via the rclone rc API (`config/update`) without restarting the NFS server. The rc endpoint SHALL NOT be reachable from outside the gateway pod. Refresh failures SHALL be logged in a structured, alertable form and reflected in gateway health state, while rclone continues retrying queued operations.

The refresher's use of `config/update` SHALL satisfy the constraints validated by the spike (finding F4): (a) the gateway's rclone config SHALL live on a **writable** volume (the config is copied from its Secret to a writable path at startup), because `config/update` persists to the config file and a read-only mount fails; (b) the token SHALL be passed explicitly as the `token` parameter, never in a form that triggers rclone's interactive OAuth flow; and (c) the rc call SHALL be timeout-guarded, since a `config/update` can block while re-initialising the backend under provider API throttling.

#### Scenario: Config on a writable volume

- **WHEN** the gateway starts
- **THEN** its rclone configuration is on a writable volume so the refresher's `config/update` calls can persist, rather than a read-only Secret mount that would fail the update

#### Scenario: Token rotated without interruption

- **WHEN** the refresher obtains a new access token while tasks hold open NFS mounts
- **THEN** the token is applied via the rc API and in-flight and subsequent cloud operations proceed without the NFS server restarting

#### Scenario: Refresh failure is not silent

- **WHEN** the errand token endpoint is unreachable at refresh time
- **THEN** the gateway health state reports the auth failure and a structured error is logged, and pending writes remain queued for retry

### Requirement: Network exposure restricted

The gateway's NFS port SHALL only be reachable from task-runner containers and the errand server. On Kubernetes this SHALL be enforced with a NetworkPolicy selecting task-runner Job pods and the server by their existing labels. Because kubelet performs the task Job's NFS mount from the **node** network namespace (mount traffic arrives from the node IP, not the task-runner pod IP), the NetworkPolicy SHALL additionally permit the configured node/pod CIDRs (`ipBlock`), or the mount is blocked; this is exposed as a required, operator-configured value. On docker-compose the port is published to the host loopback for the host-performed NFS mount. NFSv3 itself carries no authentication and SHALL NOT be exposed outside the deployment's network boundary.

#### Scenario: Unrelated pod cannot reach the gateway

- **WHEN** a pod that is not a task-runner Job and not the errand server attempts to connect to the gateway NFS port on Kubernetes
- **THEN** the connection is denied by NetworkPolicy

### Requirement: Gateway runs as a restart-managed, crash-resilient workload

The gateway SHALL run as a restart-managed workload (a Deployment on Kubernetes; a `restart: unless-stopped`-equivalent service on compose), never a bare Pod, because `rclone serve nfs` can terminate under load or an upstream error storm (the spike observed a single crash, exit 2, during a provider `403` rate-limit storm — finding F1). Combined with the persistent VFS cache (D2), a crash-and-restart SHALL NOT lose queued writes. Task-facing documentation SHALL state that a gateway restart invalidates NFS handles held by mounted task pods (`ESTALE`); with `soft` mounts those tasks see I/O errors rather than transparent recovery (finding F3), which is why the gateway lifecycle is decoupled from the server roll.

#### Scenario: Gateway crash auto-recovers without data loss

- **WHEN** the rclone serve process terminates unexpectedly with writes queued in the VFS cache
- **THEN** the workload controller restarts it and the queued writes complete from the persistent cache on restart

### Requirement: Gateway health is observable

The gateway SHALL expose health information sufficient for the settings UI and for log-based alerting: last successful cloud authentication/refresh time, pending upload count, and auth state. (The refresher reports token-refresh timing as the freshness proxy — rclone's ChangeNotify polling does not expose a discrete "last poll" timestamp via the rc API; the effective poll cadence is documented in design.md, finding F6.)

#### Scenario: Health readable while degraded

- **WHEN** the gateway has lost cloud connectivity but is still serving cached files
- **THEN** health output shows an error/stale auth state (a failed or stale last-refresh time) and a non-zero pending upload count

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

### Requirement: Dirty entries are bounded regardless of open-handle state

A dirty cache entry SHALL NOT be exempt from write-back progress expectations or from stuck-upload detection solely because a client holds it open. NFSv3 has no `CLOSE` operation, so a task container terminated mid-mount leaves the entry permanently in-use; a close-triggered write-back delay alone therefore permits a dirty entry to remain unuploaded indefinitely (observed in production as `in use 2` sustained for over 24 hours with no upload ever queued).

The gateway SHALL bound how long an entry may remain dirty irrespective of open-handle state. Past an operator-configurable maximum dirty age, an entry that has never been queued SHALL be reported as degraded write-back health with a structured error identifying the path and the pinned-by-handle condition.

Forcing a flush of a pinned entry SHALL be opt-in and disabled by default, because a client may still be writing it and publishing a torn state is the failure this requirement exists to prevent. Reporting SHALL be the default behaviour: a stalled-but-reported write is recoverable, a torn published write may not be.

No safe mechanism for forcing currently exists: rclone's rc API can reorder items already in the upload queue but cannot flush a dirty item that was never queued. Enabling the option SHALL therefore report that forcing is unavailable and continue to surface the entry, rather than reaching around the VFS to publish a file a client may still hold open. Recovery of a pinned entry is an operator procedure (see "Gateway operational runbook").

#### Scenario: Handle held open past the bound is reported

- **WHEN** a cache entry has been dirty past the configured maximum dirty age and has never been queued for upload, while still marked in-use
- **THEN** the gateway reports degraded write-back health and logs a structured error naming the path and identifying the entry as pinned by an open handle

#### Scenario: Abandoned mount does not silently strand a write

- **WHEN** a task container is terminated without unmounting after writing a file
- **THEN** the entry does not remain dirty and unreported — it is either uploaded or surfaced as degraded within the configured bound

### Requirement: Gateway operational runbook

The repository SHALL contain an operational runbook for the workspace gateway covering, at minimum: the safe procedure for taking the gateway out of service, how to detect a stalled write-back, and how to recover content from a stalled or quarantined cache entry.

The runbook SHALL state that the gateway deployment is managed by a continuous-delivery controller with self-heal enabled, so an unsuspended replica scale-down is reverted automatically and the resulting restart flushes dirty cache entries. It SHALL document suspending automated sync before any maintenance that stops the gateway, and SHALL require taking a backup of both the cache-side and cloud-side copies of any dirty path before a reconcile or restart is attempted.

#### Scenario: Operator takes the gateway down safely

- **WHEN** an operator needs to stop the gateway to act on its cache
- **THEN** the runbook directs them to suspend automated sync first, confirm no task containers are mounting the export, and back up both copies of any dirty path before proceeding

#### Scenario: Operator recovers a stalled write

- **WHEN** the gateway reports degraded write-back health naming a path
- **THEN** the runbook describes how to retrieve that path's cached content and reconcile it against the cloud copy without losing either version

### Requirement: Gateway is the sole writer of task-written paths

For any path that tasks write through the mount, the cloud folder SHALL be treated as owned by the gateway. A second sync client writing the same paths concurrently (for example a human's native Google Drive or OneDrive desktop client syncing the same folder) is unsupported: such concurrent external writes can overwrite a gateway write-back or cause the VFS to discard a local dirty entry on the next change-poll. Deployment documentation SHALL state this constraint and direct operators to scope the cloud folder to gateway-owned content or exclude task-written subpaths from other sync clients. Where feasible, the gateway SHALL log a structured warning when a locally-dirty object's remote fingerprint changes underneath it, since that is the observable symptom of a second writer.

#### Scenario: Concurrent external writer overwrites a task write

- **WHEN** a native desktop sync client re-uploads its own older copy of a file that a task has just written through the mount
- **THEN** this is a known, documented failure mode; the deployment guidance directs operators to prevent a second writer on task-written paths, and the gateway logs a structured warning identifying the contended path rather than silently reconciling in the external writer's favour

