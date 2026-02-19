## MODIFIED Requirements

### Requirement: DinD sidecar in worker deployment
The Helm chart worker Deployment SHALL NOT include a DinD sidecar container. The worker container SHALL have `CONTAINER_RUNTIME` set to `kubernetes`. The worker container SHALL have `DOCKER_HOST` removed from its environment. The worker container SHALL NOT require `privileged: true` in its security context.

The worker Deployment SHALL include a Playwright MCP sidecar container alongside the worker container. The Playwright sidecar SHALL use the image from `.Values.playwright.image` with the command `--port <port> --host 0.0.0.0 --allowed-hosts *`. The Playwright sidecar SHALL have a memory limit from `.Values.playwright.memoryLimit`. The worker container SHALL have `POD_IP` set via the Downward API (`status.podIP`).

#### Scenario: Worker pod has no DinD sidecar
- **WHEN** the Helm chart is deployed
- **THEN** the worker pod contains two containers: `worker` and `playwright` (no `dind`)

#### Scenario: Worker pod is not privileged
- **WHEN** the worker pod starts
- **THEN** no container in the pod has `privileged: true` in its security context

#### Scenario: Worker has CONTAINER_RUNTIME set
- **WHEN** the worker container starts
- **THEN** the `CONTAINER_RUNTIME` environment variable is set to `kubernetes`

#### Scenario: Worker has POD_IP from Downward API
- **WHEN** the worker pod starts
- **THEN** the worker container has `POD_IP` set to the pod's cluster IP via `fieldRef: status.podIP`

### Requirement: Worker ServiceAccount and RBAC
The Helm chart SHALL include a ServiceAccount, Role, and RoleBinding for the worker. The Role SHALL grant permissions to create, get, list, watch, and delete `jobs.batch`; create, get, and delete `configmaps`; get and list `pods`; and get `pods/log` — all within the release namespace.

#### Scenario: ServiceAccount created
- **WHEN** the Helm chart is deployed
- **THEN** a ServiceAccount named `<release>-worker` exists in the namespace

#### Scenario: Role grants required permissions
- **WHEN** the Role is inspected
- **THEN** it includes rules for jobs, configmaps, pods, and pods/log with the specified verbs

### Requirement: DinD image no longer configurable
The Helm chart values SHALL remove the `dind.image` configuration. The DinD-related values section SHALL be removed.

#### Scenario: No DinD values
- **WHEN** the Helm chart is deployed with default values
- **THEN** no DinD-related configuration exists

## REMOVED Requirements

### Requirement: DinD sidecar in worker deployment
**Reason**: The worker now uses K8s Jobs to run task-runner containers. DinD is no longer needed for production deployments.
**Migration**: Remove the `dind` container from the worker Deployment template. Remove `DOCKER_HOST` env var. Remove `privileged: true` security context. Remove `dind.image` from values.
