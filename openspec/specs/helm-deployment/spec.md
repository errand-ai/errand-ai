## MODIFIED Requirements

### Requirement: Helm chart deploys all application components
The Helm chart SHALL define Kubernetes resources for: server Deployment and Service, worker Deployment, database migration Job (pre-upgrade hook), and Ingress. The frontend SHALL NOT have a separate Deployment or Service — it is served by the server. The Helm values key for the main application SHALL be `server:`. Template files SHALL be named `server-deployment.yaml` and `server-service.yaml`.

The server and worker deployments SHALL render LLM provider environment variables from the `llmProviders` values array. For each entry at index `i`, the templates SHALL render `LLM_PROVIDER_{i}_NAME`, `LLM_PROVIDER_{i}_BASE_URL`, and `LLM_PROVIDER_{i}_API_KEY`. If the entry has `existingSecret` set, `LLM_PROVIDER_{i}_API_KEY` SHALL use `valueFrom.secretKeyRef` referencing that secret and `secretKeyApiKey` key; otherwise it SHALL use the `apiKey` value directly. The `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables SHALL be removed from both deployment templates.

#### Scenario: Full deployment with LLM providers
- **WHEN** `helm install` is run with `llmProviders` containing two entries
- **THEN** all components are created and both server and worker containers have `LLM_PROVIDER_0_*` and `LLM_PROVIDER_1_*` env vars

#### Scenario: No LLM providers configured
- **WHEN** `helm install` is run with `llmProviders` as empty array
- **THEN** no `LLM_PROVIDER_*` env vars are rendered in server or worker deployments

#### Scenario: Provider with existingSecret
- **WHEN** a provider entry has `existingSecret: "my-secret"` and `secretKeyApiKey: "api-key"`
- **THEN** the `LLM_PROVIDER_{i}_API_KEY` env var uses `valueFrom.secretKeyRef` with name "my-secret" and key "api-key"

### Requirement: Server deployment template
The server deployment template SHALL include Kubernetes liveness and readiness probes for the server container, using httpGet against the `/api/health` endpoint.

#### Scenario: Probes rendered in server deployment
- **WHEN** the Helm chart is rendered with default values
- **THEN** the server container spec SHALL include `livenessProbe` and `readinessProbe` blocks with httpGet configuration

### Requirement: Worker deployment template
The worker deployment template SHALL include Kubernetes liveness and readiness probes for the worker container, expose the health port, and pass the `HEALTH_PORT` environment variable.

#### Scenario: Probes rendered in worker deployment
- **WHEN** the Helm chart is rendered with default values
- **THEN** the worker container spec SHALL include `livenessProbe` and `readinessProbe` blocks with httpGet configuration on the worker health port

### Requirement: Helm values defaults
The values.yaml SHALL include default probe configuration for both server and worker.

#### Scenario: Default health values present
- **WHEN** values.yaml is read
- **THEN** `worker.healthPort` SHALL default to `8080`
