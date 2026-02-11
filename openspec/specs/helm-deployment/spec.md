## ADDED Requirements

### Requirement: Helm chart deploys all application components
The Helm chart SHALL define Kubernetes resources for: frontend Deployment and Service, backend Deployment and Service, worker Deployment, database migration Job (pre-upgrade hook), and Ingress.

#### Scenario: Full deployment
- **WHEN** `helm install` is run with required values
- **THEN** all components are created: frontend, backend, worker deployments, services, migration job, and ingress

### Requirement: Ingress resource for external access
The Helm chart SHALL include an Ingress resource with path-based routing on a single FQDN. The default path SHALL route to the frontend Service. Paths prefixed `/api` and `/auth` SHALL route to the backend Service. The `/metrics` path SHALL NOT be exposed via the Ingress. The Ingress host and TLS settings SHALL be configurable via values.

#### Scenario: Default path routes to frontend
- **WHEN** a request arrives at the Ingress host with path `/`
- **THEN** it is routed to the frontend Service

#### Scenario: API path routes to backend
- **WHEN** a request arrives with path `/api/tasks`
- **THEN** it is routed to the backend Service

#### Scenario: Auth path routes to backend
- **WHEN** a request arrives with path `/auth/login`
- **THEN** it is routed to the backend Service

#### Scenario: Metrics path is not exposed
- **WHEN** a request arrives with path `/metrics/queue`
- **THEN** the Ingress does not match and the request is not routed (404)

### Requirement: KEDA ScaledObject for worker autoscaling
The Helm chart SHALL include a KEDA ScaledObject targeting the worker Deployment. It SHALL use an HTTP-based trigger polling the backend's `GET /metrics/queue` endpoint. The worker SHALL scale from 0 to a configurable maximum based on `queue_depth`.

#### Scenario: Workers scale up on pending tasks
- **WHEN** the backend reports `queue_depth > 0`
- **THEN** KEDA scales the worker Deployment to at least 1 replica

#### Scenario: Workers scale to zero when idle
- **WHEN** the backend reports `queue_depth: 0` for the cooldown period
- **THEN** KEDA scales the worker Deployment to 0 replicas

### Requirement: Backend supports multiple replicas
The backend Deployment SHALL have a configurable `replicaCount` (default 2) and use a rolling update strategy. The Service SHALL load-balance across all backend pods.

#### Scenario: Multiple backend replicas
- **WHEN** `replicaCount` is set to 3
- **THEN** 3 backend pods are created and the Service distributes traffic across them

### Requirement: Database URL provided via Secret
The Helm chart SHALL reference a Kubernetes Secret for the `DATABASE_URL` environment variable. The Secret MUST be created externally (not managed by the chart).

#### Scenario: Secret reference
- **WHEN** the chart is deployed with `database.existingSecret` set to `"content-manager-db"`
- **THEN** all pods (backend, worker, migration job) mount `DATABASE_URL` from that Secret

### Requirement: Container image references are configurable
The Helm chart SHALL allow overriding the image repository and tag for frontend and backend/worker images via values.

#### Scenario: Custom image tag
- **WHEN** `image.tag` is set to `0.2.0`
- **THEN** all deployments use that image tag

### Requirement: Keycloak credentials provided via Secret
The Helm chart SHALL reference a Kubernetes Secret for `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` environment variables on the backend Deployment. The Secret MUST be created externally (not managed by the chart). The `OIDC_DISCOVERY_URL` SHALL be configurable via values. The backend Deployment SHALL also receive `OPENAI_BASE_URL` from values and `OPENAI_API_KEY` from the existing Secret (replacing the previous `LITELLM_BASE_URL` and `LITELLM_API_KEY` environment variable names). The worker Deployment SHALL receive `OPENAI_BASE_URL` and `OPENAI_API_KEY` via the same mechanism as the backend.

#### Scenario: Secret reference for OIDC credentials
- **WHEN** the chart is deployed with `keycloak.existingSecret` set to `"content-manager-keycloak"`
- **THEN** the backend pods mount `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` from that Secret

#### Scenario: Discovery URL from values
- **WHEN** `keycloak.discoveryUrl` is set in values
- **THEN** the backend pods have `OIDC_DISCOVERY_URL` set to that value

#### Scenario: OpenAI environment variables on backend
- **WHEN** the chart is deployed with `openai.baseUrl` and `openai.existingSecret` configured
- **THEN** the backend pods have `OPENAI_BASE_URL` and `OPENAI_API_KEY` set from values and the Secret respectively

#### Scenario: OpenAI environment variables on worker
- **WHEN** the chart is deployed
- **THEN** the worker pods have `OPENAI_BASE_URL` and `OPENAI_API_KEY` set, matching the backend configuration

### Requirement: DinD sidecar in worker deployment
The Helm chart worker Deployment SHALL include a `docker:dind` sidecar container alongside the worker container. The DinD container SHALL run with `privileged: true` in the security context. The DinD container SHALL have `DOCKER_TLS_CERTDIR` set to an empty string to disable TLS. The worker container SHALL have `DOCKER_HOST` set to `tcp://localhost:2375` to communicate with the DinD sidecar via the pod's shared network namespace.

#### Scenario: Worker pod includes DinD sidecar
- **WHEN** the Helm chart is deployed
- **THEN** the worker pod contains two containers: `worker` and `dind`

#### Scenario: DinD runs privileged
- **WHEN** the worker pod starts
- **THEN** the `dind` container has `privileged: true` in its security context

#### Scenario: Worker connects to DinD
- **WHEN** the worker container starts
- **THEN** the `DOCKER_HOST` environment variable is set to `tcp://localhost:2375`

### Requirement: Task runner image configurable in values
The Helm chart values SHALL include a `taskRunner.image.repository` and `taskRunner.image.tag` configuration. The `tag` SHALL default to the chart's `appVersion` (same as frontend and backend images). The worker container SHALL have a `TASK_RUNNER_IMAGE` environment variable set to the fully-qualified task runner image reference.

#### Scenario: Default task runner image tag
- **WHEN** `taskRunner.image.tag` is empty in values
- **THEN** the worker container's `TASK_RUNNER_IMAGE` env var uses the chart's `appVersion` as the tag

#### Scenario: Custom task runner image tag
- **WHEN** `taskRunner.image.tag` is set to `1.0.0` in values
- **THEN** the worker container's `TASK_RUNNER_IMAGE` env var uses `1.0.0` as the tag

### Requirement: DinD image configurable in values
The Helm chart values SHALL include a `dind.image` configuration (default `docker:27-dind`) for the DinD sidecar image.

#### Scenario: Default DinD image
- **WHEN** `dind.image` is not set in values
- **THEN** the DinD sidecar uses `docker:27-dind`

#### Scenario: Custom DinD image
- **WHEN** `dind.image` is set to `docker:26-dind` in values
- **THEN** the DinD sidecar uses `docker:26-dind`
