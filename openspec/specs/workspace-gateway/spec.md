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

