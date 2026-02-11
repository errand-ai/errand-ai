## MODIFIED Requirements

### Requirement: Helm chart deploys all application components
The Helm chart SHALL define Kubernetes resources for: frontend Deployment and Service, backend Deployment and Service, worker Deployment, database migration Job (pre-upgrade hook), and Ingress.

#### Scenario: Full deployment
- **WHEN** `helm install` is run with required values
- **THEN** all components are created: frontend, backend, worker deployments, services, migration job, and ingress

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
