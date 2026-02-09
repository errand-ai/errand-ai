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
The Helm chart SHALL reference a Kubernetes Secret for `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` environment variables on the backend Deployment. The Secret MUST be created externally (not managed by the chart). The `OIDC_DISCOVERY_URL` SHALL be configurable via values.

#### Scenario: Secret reference for OIDC credentials
- **WHEN** the chart is deployed with `keycloak.existingSecret` set to `"content-manager-keycloak"`
- **THEN** the backend pods mount `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` from that Secret

#### Scenario: Discovery URL from values
- **WHEN** `keycloak.discoveryUrl` is set in values
- **THEN** the backend pods have `OIDC_DISCOVERY_URL` set to that value
