## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Frontend Deployment and Service (implicit in original "deploys all application components")
**Reason**: The frontend is now served by the backend. The separate frontend Deployment, Service, and ConfigMap are no longer needed.
**Migration**: Delete `frontend-deployment.yaml`, `frontend-service.yaml`, and `frontend-configmap.yaml` from the Helm templates. Remove `frontend` section from `values.yaml`.
