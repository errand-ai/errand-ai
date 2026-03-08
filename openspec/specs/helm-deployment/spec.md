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
