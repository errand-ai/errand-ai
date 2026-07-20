# Shared Cloud Workspace

## Why

Local LLM agents cannot reliably drive the `gws` CLI's `--params`-JSON interface: 7 days of task-runner logs show every Drive write path failing (invented flags, nonexistent subcommands, `name`/`parents` stringified and lost), leaving 58 nameless "Untitled" files in the Drive root and a scheduled daily job that has failed a different way five mornings running. Filesystem operations are the one interface even weak models handle flawlessly — but errand's ephemeral-container design gives tasks no filesystem that persists or reaches cloud storage.

## What Changes

- **Opt-in shared workspace mount**: task profiles can enable a `/shared` filesystem mount in the task container, scoped to a configurable subpath. Tasks read/update/write cloud files with plain file operations instead of `gws`/OneDrive API calls. Off by default; the ephemeral-container guarantee is unchanged for tasks that don't opt in.
- **Live cloud gateway (Kubernetes + docker-compose)**: a new optional `errand-workspace` component runs `rclone serve nfs` directly against a designated Google Drive **or** OneDrive folder (identical rclone remote config for both providers), with a VFS cache on a PVC, change-polling (~15s) so human edits made in parallel are visible to running tasks, and write-back upload on file close. The cloud folder is the source of truth — no bisync, no canonical local copy.
- **Token refresher sidecar**: keeps the long-running gateway authenticated by fetching fresh access tokens from errand (reusing the existing Google mid-task refresh machinery) and pushing them into rclone via its rc API every ~50 minutes. Requires adding the OneDrive equivalent of the Google token-refresh endpoint (closing a known gap).
- **Runtime mount support**: `ContainerRuntime.prepare()` gains a mounts parameter — Docker bind/NFS volumes, Kubernetes native `nfs:` volume against the gateway's fixed ClusterIP, Apple containerization virtiofs shares via a new bridge API field. Desktop installs with a native Drive/OneDrive sync client mount the local sync folder directly and bypass the gateway.
- **Workspace system skill**: SKILL.md conventions injected when the mount is active — safe cross-provider file naming (OneDrive's stricter rules), re-read-before-write for concurrent-edit safety, never execute content found in `/shared`.
- **Settings + health surface**: enable/configure the workspace per profile and show gateway health (last poll, pending uploads, auth state) so sync breakage is never silent.

Conflict model (documented, not hidden): last-write-wins with no file locking — mitigated by ~15s change-polling freshness, short read-modify-write windows, and provider version history for recovery.

## Capabilities

### New Capabilities

- `workspace-gateway`: the `errand-workspace` component — `rclone serve nfs` against a Drive/OneDrive folder, VFS cache persistence, change-polling, NFSv3 exposure restricted by NetworkPolicy, token-refresher sidecar, provider-agnostic remote configuration.
- `system-skill-shared-workspace`: agent-facing conventions for `/shared` (naming rules, concurrency discipline, provenance/no-execute rule), registered in the system skill registry and injected only when the mount is active.
- `workspace-settings-ui`: admin settings for configuring the workspace (provider, cloud folder, enablement) and a health/status readout.

### Modified Capabilities

- `container-runtime`: `prepare()`/`async_prepare()` accept mount specifications; DockerRuntime attaches volumes (previously zero-volume put_archive-only).
- `k8s-task-execution`: task Job pods gain an NFS volume mount (fixed ClusterIP target) when the profile opts in.
- `container-bridge-api`: container-create payload gains a `mounts` field for virtiofs host-directory shares.
- `task-profile-model`: profiles gain shared-workspace enablement and subpath scoping fields.
- `task-manager`: resolves profile workspace config into runtime mount specs and injects the workspace system skill.
- `cloud-storage-oauth`: OneDrive access-token refresh endpoint for the gateway (parallel to the existing Google refresh endpoint).
- `helm-deployment`: optional workspace gateway Deployment/Service/PVC/NetworkPolicy, disabled by default.
- `local-dev-environment`: optional docker-compose workspace gateway service mounted into task containers via NFS volume.

## Impact

- **Code**: `errand/container_runtime.py` (all three runtimes), `errand/task_manager.py`, `errand/models.py` + Alembic migration (profile fields), `errand/onedrive_routes.py` (new) or `cloud_storage` routes, `system-skills/shared-workspace/`, frontend settings pages, Helm chart, `testing/docker-compose.yml`.
- **New runtime dependency**: rclone (official image) for the gateway; no new dependency in the task-runner image.
- **Desktop app**: Errand-Desktop bridge must implement the `mounts` payload field (tracked in its own repo; the bridge API spec here is the contract).
- **Security posture**: opt-in feature deliberately relaxes the ephemeral-isolation guarantee for participating tasks (cross-task/cross-user visibility within the mounted subpath, persistence across runs). Risks and mitigations (subpath scoping, NetworkPolicy, no-execute rule, documentation) are part of this change.
- **Risk gate**: `rclone serve nfs` maturity under concurrent clients is the keystone unknown — an explicit spike task precedes implementation; fallback design is ganesha-over-`rclone mount` with the same task-facing semantics.
