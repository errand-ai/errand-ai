## Purpose

The Helm chart for deploying errand to Kubernetes: a single server Deployment that serves the API and processes tasks (integrated TaskManager, no separate worker), plus its Service, database migration Job, Ingress, Playwright Deployment/Service, and the server ServiceAccount with the RBAC needed to run task Jobs.
## Requirements
### Requirement: Helm chart deploys all application components

The Helm chart SHALL define Kubernetes resources for: server Deployment and Service, database migration Job (pre-upgrade hook), Ingress, Playwright Deployment and Service, and server ServiceAccount with RBAC. The Helm chart SHALL NOT include a separate worker Deployment. The server Deployment SHALL handle both API serving and task processing (via the integrated TaskManager).

The server Deployment SHALL include environment variables previously only on the worker: `CONTAINER_RUNTIME=kubernetes`, `TASK_RUNNER_IMAGE`, `ERRAND_MCP_URL` (pointing to itself), `PLAYWRIGHT_MCP_URL` (pointing to Playwright Service), and all credential/integration variables. The `POD_IP` downward API field SHALL be removed (no longer needed for Playwright routing).

The server's ServiceAccount SHALL have RBAC rules for: jobs (create, get, list, delete), configmaps (create, get, delete), pods (get, list), pods/log (get), and pods/exec (create). These are the same permissions previously on the worker's ServiceAccount.

The server and worker deployments SHALL render LLM provider environment variables from the `llmProviders` values array. For each entry at index `i`, the templates SHALL render `LLM_PROVIDER_{i}_NAME`, `LLM_PROVIDER_{i}_BASE_URL`, and `LLM_PROVIDER_{i}_API_KEY`. If the entry has `existingSecret` set, `LLM_PROVIDER_{i}_API_KEY` SHALL use `valueFrom.secretKeyRef` referencing that secret and `secretKeyApiKey` key; otherwise it SHALL use the `apiKey` value directly.

#### Scenario: Full deployment without separate worker

- **WHEN** `helm install` is run
- **THEN** server Deployment, Playwright Deployment, and ServiceAccount with RBAC are created; no worker Deployment exists

#### Scenario: Server has task processing env vars

- **WHEN** the server Deployment is rendered
- **THEN** it includes `CONTAINER_RUNTIME`, `TASK_RUNNER_IMAGE`, `ERRAND_MCP_URL`, and `PLAYWRIGHT_MCP_URL`

#### Scenario: Server ServiceAccount has RBAC for Jobs

- **WHEN** the server Deployment runs
- **THEN** it can create, get, list, and delete K8s Jobs and ConfigMaps in its namespace

### Requirement: Server deployment template
The server deployment template SHALL include Kubernetes liveness and readiness probes for the server container, using httpGet against the `/api/health` endpoint.

#### Scenario: Probes rendered in server deployment
- **WHEN** the Helm chart is rendered with default values
- **THEN** the server container spec SHALL include `livenessProbe` and `readinessProbe` blocks with httpGet configuration

<!-- Removed: Worker deployment template — Worker functionality merged into the server's TaskManager. -->

### Requirement: Helm values defaults
The values.yaml SHALL include default probe configuration for the server. The values.yaml SHALL NOT default any key that binds to a `SETTINGS_REGISTRY` entry with an `env_var`, because such a default silently makes that setting readonly in the admin settings API on every deployment.

#### Scenario: Default health values present
- **WHEN** values.yaml is read
- **THEN** server probe configuration SHALL be present with defaults

#### Scenario: No env-bound tunable is defaulted
- **WHEN** the chart is rendered with default values
- **THEN** no env var backing a `SETTINGS_REGISTRY` key SHALL be emitted solely because of a `values.yaml` default

### Requirement: Playwright Deployment and Service

The Helm chart SHALL include a Playwright Deployment and Service when `playwright.enabled` is `true`. The Deployment SHALL use the `playwright.image` values with args `["--isolated", "--port", "<port>", "--host", "0.0.0.0", "--allowed-hosts", "*"]`. The Service SHALL expose the Playwright port for internal cluster access. The server Deployment SHALL set `PLAYWRIGHT_MCP_URL` to the Playwright Service's internal DNS URL.

#### Scenario: Playwright enabled

- **WHEN** `playwright.enabled` is `true`
- **THEN** a Playwright Deployment and Service are created, and the server's `PLAYWRIGHT_MCP_URL` points to the Service

#### Scenario: Playwright disabled

- **WHEN** `playwright.enabled` is `false`
- **THEN** no Playwright Deployment or Service is created, and `PLAYWRIGHT_MCP_URL` is not set

### Requirement: max_concurrent_tasks in server env vars

The Helm chart SHALL pass `MAX_CONCURRENT_TASKS` to the server Deployment from `values.server.maxConcurrentTasks` if set. `values.yaml` SHALL NOT provide a default for `server.maxConcurrentTasks`, so a default install emits no `MAX_CONCURRENT_TASKS` env var and the setting resolves from the database (or the registry default) and remains editable via `PUT /api/settings`.

#### Scenario: Custom concurrency limit

- **WHEN** `server.maxConcurrentTasks` is set to 5
- **THEN** the server Deployment includes `MAX_CONCURRENT_TASKS=5`

#### Scenario: Default install leaves concurrency editable

- **WHEN** the chart is rendered with no `server.maxConcurrentTasks` value
- **THEN** the server Deployment SHALL NOT include a `MAX_CONCURRENT_TASKS` env var
- **AND** `GET /api/settings` SHALL report `max_concurrent_tasks` with `readonly: false`

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

