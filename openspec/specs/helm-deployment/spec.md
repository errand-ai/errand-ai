## Requirements

### Requirement: Helm chart deploys all application components
The Helm chart SHALL define Kubernetes resources for: server Deployment and Service, worker Deployment, database migration Job (pre-upgrade hook), and Ingress. The frontend SHALL NOT have a separate Deployment or Service — it is served by the server. The Helm values key for the main application SHALL be `server:` (not `backend:`). Template files SHALL be named `server-deployment.yaml` and `server-service.yaml`.

#### Scenario: Full deployment
- **WHEN** `helm install` is run with required values
- **THEN** all components are created: server deployment and service, worker deployment, migration job, and ingress — but no frontend deployment or service

### Requirement: Ingress resource for external access
The Helm chart SHALL include an Ingress resource that routes all paths on a single FQDN to the server Service. The `/` catch-all path SHALL route to the server Service (which serves both API routes and frontend static files). Paths prefixed `/api`, `/auth`, `/mcp`, and `/slack` SHALL also route to the server Service. The `/metrics` path SHALL NOT be exposed via the Ingress. The Ingress host and TLS settings SHALL be configurable via values. The ingress backend service name SHALL be `{{ include "errand.fullname" . }}` (without a `-backend` suffix).

#### Scenario: Default path routes to server
- **WHEN** a request arrives at the Ingress host with path `/`
- **THEN** it is routed to the server Service which serves the frontend SPA

#### Scenario: API path routes to server
- **WHEN** a request arrives with path `/api/tasks`
- **THEN** it is routed to the server Service

#### Scenario: Auth path routes to server
- **WHEN** a request arrives with path `/auth/login`
- **THEN** it is routed to the server Service

#### Scenario: Slack webhook routed to server
- **WHEN** an external request arrives at `/slack/commands`
- **THEN** the ingress routes it to the server service

#### Scenario: Metrics path is not exposed
- **WHEN** a request arrives with path `/metrics/queue`
- **THEN** the Ingress does not match and the request is not routed (404)

### Requirement: Container image references are configurable
The Helm chart SHALL allow overriding the image repository and tag for the server/worker image via `server.image` values. There SHALL NOT be a separate frontend image configuration. The default image repository SHALL be `ghcr.io/errand-ai/errand`.

#### Scenario: Custom image tag
- **WHEN** `server.image.tag` is set to `0.2.0`
- **THEN** the server and worker deployments use that image tag

### Requirement: Worker deployment with Playwright sidecar
The Helm chart worker Deployment SHALL NOT include a DinD sidecar container. The worker container SHALL have `CONTAINER_RUNTIME` set to `kubernetes`. The worker container SHALL have `DOCKER_HOST` removed from its environment. The worker container SHALL NOT require `privileged: true` in its security context. The worker container SHALL have `ERRAND_MCP_URL` set to `http://{{ include "errand.fullname" . }}:{{ .Values.server.service.port }}/mcp`.

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

#### Scenario: Worker has ERRAND_MCP_URL set
- **WHEN** the worker container starts
- **THEN** the `ERRAND_MCP_URL` environment variable points to the server service MCP endpoint

### Requirement: Worker ServiceAccount and RBAC
The Helm chart SHALL include a ServiceAccount, Role, and RoleBinding for the worker. The Role SHALL grant permissions to create, get, list, watch, and delete `jobs.batch`; create, get, list, and delete `configmaps`; get and list `pods`; get `pods/log`; and create `pods/exec` — all within the release namespace. The `pods/exec` permission is needed by `KubernetesRuntime.result()` to read `/output/result.json` from completed task-runner pods.

#### Scenario: ServiceAccount created
- **WHEN** the Helm chart is deployed
- **THEN** a ServiceAccount named `<release>-worker` exists in the namespace

#### Scenario: Role grants required permissions
- **WHEN** the Role is inspected
- **THEN** it includes rules for jobs, configmaps, pods, and pods/log with the specified verbs

### Requirement: Perplexity MCP deployment
The Helm chart SHALL include a Deployment for the Perplexity MCP server, rendered when `.Values.perplexity.enabled` is `true` (default). The Deployment SHALL use the image `{{ .Values.perplexity.image.repository }}:{{ .Values.perplexity.image.tag }}`. The Deployment SHALL have a configurable `replicaCount` (default 1). The container SHALL have a `BACKEND_URL` environment variable set to the backend service URL (`http://{{ include "errand.fullname" . }}:{{ .Values.server.service.port }}`). The container SHALL expose port 8080. The Deployment SHALL NOT reference any Kubernetes Secret via `envFrom`.

#### Scenario: Perplexity deployed by default
- **WHEN** the chart is deployed with default values (`.Values.perplexity.enabled` is `true`)
- **THEN** the chart renders a Perplexity Deployment with `BACKEND_URL` env var pointing to the backend service

#### Scenario: Perplexity disabled
- **WHEN** `.Values.perplexity.enabled` is set to `false`
- **THEN** the chart does not render the Perplexity Deployment or Service

#### Scenario: No secret reference
- **WHEN** the Perplexity Deployment is rendered
- **THEN** the container does not have `envFrom` referencing any Kubernetes Secret

### Requirement: Perplexity MCP Service
The Helm chart SHALL include a Service for the Perplexity MCP Deployment, rendered when `.Values.perplexity.enabled` is `true`. The Service SHALL target port 8080 and expose it on a configurable service port (default 8080). The Service SHALL select pods from the Perplexity Deployment.

#### Scenario: Service routes to Perplexity pods
- **WHEN** `.Values.perplexity.enabled` is `true` and the Perplexity Deployment has 2 replicas
- **THEN** the Service named `<release>-perplexity-mcp` load-balances across both pods on port 8080

#### Scenario: Service not rendered when disabled
- **WHEN** `.Values.perplexity.enabled` is set to `false`
- **THEN** the chart does not render the Perplexity Service

### Requirement: Worker Perplexity environment variables
The worker Deployment SHALL include a `PERPLEXITY_URL` environment variable set to the Perplexity MCP service URL (`http://{{ include "errand.fullname" . }}-perplexity-mcp:{{ .Values.perplexity.service.port }}/mcp`) when `.Values.perplexity.enabled` is `true`. The worker Deployment SHALL NOT include `USE_PERPLEXITY` environment variable.

#### Scenario: Worker has PERPLEXITY_URL when enabled
- **WHEN** `.Values.perplexity.enabled` is `true`
- **THEN** the worker container has `PERPLEXITY_URL` set to the Perplexity service URL

#### Scenario: Worker has no Perplexity env vars when disabled
- **WHEN** `.Values.perplexity.enabled` is `false`
- **THEN** the worker container does not have `PERPLEXITY_URL` or `USE_PERPLEXITY` environment variables
