## Requirements

### Requirement: Helm chart deploys all application components
The Helm chart SHALL define Kubernetes resources for: backend Deployment and Service, worker Deployment, database migration Job (pre-upgrade hook), and Ingress. The frontend SHALL NOT have a separate Deployment or Service — it is served by the backend.

#### Scenario: Full deployment
- **WHEN** `helm install` is run with required values
- **THEN** all components are created: backend deployment and service, worker deployment, migration job, and ingress — but no frontend deployment or service

### Requirement: Ingress resource for external access
The Helm chart SHALL include an Ingress resource that routes all paths on a single FQDN to the backend Service. The `/` catch-all path SHALL route to the backend Service (which serves both API routes and frontend static files). Paths prefixed `/api`, `/auth`, `/mcp`, and `/slack` SHALL also route to the backend Service. The `/metrics` path SHALL NOT be exposed via the Ingress. The Ingress host and TLS settings SHALL be configurable via values.

#### Scenario: Default path routes to backend
- **WHEN** a request arrives at the Ingress host with path `/`
- **THEN** it is routed to the backend Service which serves the frontend SPA

#### Scenario: API path routes to backend
- **WHEN** a request arrives with path `/api/tasks`
- **THEN** it is routed to the backend Service

#### Scenario: Auth path routes to backend
- **WHEN** a request arrives with path `/auth/login`
- **THEN** it is routed to the backend Service

#### Scenario: Slack webhook routed to backend
- **WHEN** an external request arrives at `/slack/commands`
- **THEN** the ingress routes it to the backend service

#### Scenario: Metrics path is not exposed
- **WHEN** a request arrives with path `/metrics/queue`
- **THEN** the Ingress does not match and the request is not routed (404)

### Requirement: Container image references are configurable
The Helm chart SHALL allow overriding the image repository and tag for the backend/worker image via values. There SHALL NOT be a separate frontend image configuration.

#### Scenario: Custom image tag
- **WHEN** `image.tag` is set to `0.2.0`
- **THEN** the backend and worker deployments use that image tag

### Requirement: Worker deployment with Playwright sidecar
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
The Helm chart SHALL include a ServiceAccount, Role, and RoleBinding for the worker. The Role SHALL grant permissions to create, get, list, watch, and delete `jobs.batch`; create, get, list, and delete `configmaps`; get and list `pods`; get `pods/log`; and create `pods/exec` — all within the release namespace. The `pods/exec` permission is needed by `KubernetesRuntime.result()` to read `/output/result.json` from completed task-runner pods.

#### Scenario: ServiceAccount created
- **WHEN** the Helm chart is deployed
- **THEN** a ServiceAccount named `<release>-worker` exists in the namespace

#### Scenario: Role grants required permissions
- **WHEN** the Role is inspected
- **THEN** it includes rules for jobs, configmaps, pods, and pods/log with the specified verbs
