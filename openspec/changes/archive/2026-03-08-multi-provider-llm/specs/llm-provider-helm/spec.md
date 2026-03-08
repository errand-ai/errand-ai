## ADDED Requirements

### Requirement: Helm values for LLM providers array
The Helm chart `values.yaml` SHALL replace the `openai` values block with an `llmProviders` array. Each entry SHALL support `name` (string), `baseUrl` (string), `apiKey` (string, for inline values), `existingSecret` (string, K8s secret name), and `secretKeyApiKey` (string, key within the secret). The default `llmProviders` SHALL be an empty array.

#### Scenario: Single provider via inline values
- **WHEN** values contain `llmProviders: [{name: "litellm", baseUrl: "https://litellm.example.com/v1", apiKey: "sk-abc"}]`
- **THEN** the rendered deployment env includes `LLM_PROVIDER_0_NAME=litellm`, `LLM_PROVIDER_0_BASE_URL=https://litellm.example.com/v1`, `LLM_PROVIDER_0_API_KEY=sk-abc`

#### Scenario: Provider with existing secret
- **WHEN** values contain `llmProviders: [{name: "openai", baseUrl: "https://api.openai.com/v1", existingSecret: "openai-creds", secretKeyApiKey: "api-key"}]`
- **THEN** the deployment env includes `LLM_PROVIDER_0_NAME=openai`, `LLM_PROVIDER_0_BASE_URL=https://api.openai.com/v1`, and `LLM_PROVIDER_0_API_KEY` sourced from secret `openai-creds` key `api-key`

#### Scenario: No providers configured
- **WHEN** `llmProviders` is an empty array
- **THEN** no `LLM_PROVIDER_*` env vars are rendered

### Requirement: Deployment template renders indexed env vars
The server and worker deployment templates SHALL iterate over `.Values.llmProviders` using `range` with `$index` and render `LLM_PROVIDER_{index}_NAME`, `LLM_PROVIDER_{index}_BASE_URL`, and `LLM_PROVIDER_{index}_API_KEY` environment variables for each entry. If `existingSecret` is set, the API key SHALL use `valueFrom.secretKeyRef`; otherwise it SHALL use `value` directly. The `name` and `baseUrl` fields SHALL always use `value` directly.

#### Scenario: Two providers rendered
- **WHEN** `llmProviders` has two entries
- **THEN** the deployment has env vars `LLM_PROVIDER_0_NAME`, `LLM_PROVIDER_0_BASE_URL`, `LLM_PROVIDER_0_API_KEY`, `LLM_PROVIDER_1_NAME`, `LLM_PROVIDER_1_BASE_URL`, `LLM_PROVIDER_1_API_KEY`

#### Scenario: Mixed inline and secret API keys
- **WHEN** provider 0 has `apiKey: "sk-abc"` and provider 1 has `existingSecret: "my-secret"` with `secretKeyApiKey: "key"`
- **THEN** provider 0's API key uses `value: "sk-abc"` and provider 1's uses `valueFrom.secretKeyRef`

### Requirement: Remove legacy openai values
The Helm chart SHALL remove the `openai.baseUrl`, `openai.apiKey`, `openai.existingSecret`, and `openai.secretKeyApiKey` values. The deployment templates SHALL remove the `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables.

#### Scenario: Legacy openai values not accepted
- **WHEN** a user provides `openai.baseUrl` in their values
- **THEN** the value is ignored (no env var rendered)
