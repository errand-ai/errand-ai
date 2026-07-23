## ADDED Requirements

### Requirement: Optional workspace gateway component in the Helm chart

The Helm chart SHALL include an optional workspace gateway: a Deployment (rclone serve container + token-refresher sidecar), a Service with a configurable **static ClusterIP**, a PVC for the VFS cache, a Secret/ConfigMap for the rclone remote configuration, and a NetworkPolicy restricting NFS ingress to task-runner Jobs and the server. All of it SHALL be gated behind `workspace.enabled` (default `false`) so existing deployments are unaffected. Values SHALL cover provider (`drive`/`onedrive`), cloud folder, static ClusterIP, cache size, and poll interval. The chart documentation SHALL state the opt-in security trade-offs (shared visibility within the workspace, persistence across tasks) and the backup expectation for the cloud folder. The documentation SHALL also capture the spike-derived operational prerequisites: (a) every node that schedules task Jobs needs an NFS client (`nfs-utils`) — finding F2; (b) production SHOULD configure a **dedicated OAuth `client_id`** for the rclone remote rather than rclone's shared default, and SHOULD tune attribute/dir caching (`actimeo`, `--dir-cache-time`) and the drive pacer to keep NFS metadata ops off the provider API under concurrency — finding F5; and (c) the gateway's rclone config must be on a writable volume for the token refresher — finding F4.

#### Scenario: Operational prerequisites documented

- **WHEN** an operator reads the chart documentation before enabling the workspace
- **THEN** the node `nfs-utils` prerequisite, the dedicated-`client_id`/caching guidance, and the writable-config requirement are all stated

#### Scenario: Disabled by default

- **WHEN** the chart is installed with default values
- **THEN** no workspace resources are created and all existing templates render unchanged

#### Scenario: Enabled gateway renders

- **WHEN** `workspace.enabled=true` with provider and folder set
- **THEN** the Deployment, Service (with the configured static ClusterIP), cache PVC, and NetworkPolicy render, and the server deployment receives the workspace configuration (gateway address, export path) via env vars

#### Scenario: Gateway lifecycle decoupled from server

- **WHEN** the errand server Deployment is rolled (new release)
- **THEN** the workspace gateway pods are not restarted and task NFS mounts are undisturbed
