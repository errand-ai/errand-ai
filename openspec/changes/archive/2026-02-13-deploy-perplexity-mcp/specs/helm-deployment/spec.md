## ADDED Requirements

### Requirement: Perplexity values section in Helm chart

The Helm chart `values.yaml` SHALL include a `perplexity` section with the following defaults:
- `existingSecret`: `""` (empty string — feature disabled by default)
- `replicaCount`: `1`
- `image.repository`: `"mcp/perplexity-ask"`
- `image.tag`: `"latest"`
- `image.pullPolicy`: `"IfNotPresent"`
- `service.port`: `8000`

#### Scenario: Default values disable Perplexity

- **WHEN** the chart is installed with default values
- **THEN** no Perplexity resources are rendered

#### Scenario: Setting existingSecret enables Perplexity

- **WHEN** `perplexity.existingSecret` is set to a non-empty value
- **THEN** the Perplexity Deployment, Service, and worker env vars are all rendered

## MODIFIED Requirements

### Requirement: Keycloak credentials provided via Secret

The Helm chart SHALL reference a Kubernetes Secret for `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` environment variables on the backend Deployment. The Secret MUST be created externally (not managed by the chart). The `OIDC_DISCOVERY_URL` SHALL be configurable via values. The backend Deployment SHALL also receive `OPENAI_BASE_URL` from values and `OPENAI_API_KEY` from the existing Secret (replacing the previous `LITELLM_BASE_URL` and `LITELLM_API_KEY` environment variable names). The worker Deployment SHALL receive `OPENAI_BASE_URL` and `OPENAI_API_KEY` via the same mechanism as the backend. When `.Values.perplexity.existingSecret` is non-empty, the worker Deployment SHALL additionally receive `USE_PERPLEXITY` set to `"true"` and `PERPLEXITY_URL` set to the in-cluster Perplexity Service URL (`http://<release>-perplexity-mcp:<port>/sse`).

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

#### Scenario: Perplexity env vars on worker when enabled

- **WHEN** `.Values.perplexity.existingSecret` is set to `"perplexity-api-key"`
- **THEN** the worker pods have `USE_PERPLEXITY` set to `"true"` and `PERPLEXITY_URL` set to `http://<release>-perplexity-mcp:8000/sse`

#### Scenario: No Perplexity env vars on worker when disabled

- **WHEN** `.Values.perplexity.existingSecret` is empty or not set
- **THEN** the worker pods do not have `USE_PERPLEXITY` or `PERPLEXITY_URL` environment variables
