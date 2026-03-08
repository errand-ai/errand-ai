## ADDED Requirements

### Requirement: LLM provider database model
The backend SHALL define an `LlmProvider` SQLAlchemy model mapped to the `llm_provider` table with columns: `id` (UUID primary key, server-default), `name` (String, unique, not null), `base_url` (String, not null), `api_key_encrypted` (String, not null — Fernet-encrypted using `CREDENTIAL_ENCRYPTION_KEY`), `provider_type` (String, not null — one of `litellm`, `openai_compatible`, `unknown`), `is_default` (Boolean, not null, default False), `source` (String, not null — one of `env`, `database`), `created_at` (DateTime, server-default utcnow), `updated_at` (DateTime, server-default utcnow, onupdate utcnow). An Alembic migration SHALL create this table.

#### Scenario: Table created by migration
- **WHEN** the Alembic migration runs
- **THEN** the `llm_provider` table exists with all specified columns and constraints

#### Scenario: Provider name uniqueness enforced
- **WHEN** a provider with name "openai" already exists and another insert with name "openai" is attempted
- **THEN** the database raises a unique constraint violation

### Requirement: Provider CRUD API endpoints
The backend SHALL expose provider management endpoints requiring the `admin` role:
- `GET /api/llm/providers` — returns all providers with `api_key` masked (first 4 chars + `****`), sorted by `is_default` descending then `name` ascending
- `POST /api/llm/providers` — creates a provider; accepts `{name, base_url, api_key}`; encrypts the API key; probes the base URL to detect provider type; returns the created provider
- `PUT /api/llm/providers/{id}` — updates a provider; accepts partial `{name, base_url, api_key}`; if `base_url` changes, re-probes to update `provider_type`; returns the updated provider
- `DELETE /api/llm/providers/{id}` — deletes a provider; clears any model settings referencing it; returns 204

Env-sourced providers (`source: "env"`) SHALL NOT be modifiable via `PUT` or deletable via `DELETE` — these endpoints SHALL return HTTP 403 with `{"detail": "Cannot modify env-sourced provider"}`.

The default provider SHALL NOT be deletable — `DELETE` SHALL return HTTP 409 with `{"detail": "Cannot delete the default provider"}`.

#### Scenario: List providers
- **WHEN** an admin sends `GET /api/llm/providers` and two providers exist (one default, one not)
- **THEN** the response is a JSON array with the default provider first, API keys masked

#### Scenario: Create provider
- **WHEN** an admin sends `POST /api/llm/providers` with `{"name": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-abc123"}`
- **THEN** the provider is created with `provider_type` detected by probing, `source: "database"`, `is_default: false`
- **THEN** the response includes the provider with masked API key

#### Scenario: Create provider with duplicate name
- **WHEN** an admin sends `POST /api/llm/providers` with a name that already exists
- **THEN** the backend returns HTTP 409 with `{"detail": "Provider name already exists"}`

#### Scenario: Update provider base URL triggers re-probe
- **WHEN** an admin sends `PUT /api/llm/providers/{id}` with a new `base_url`
- **THEN** the provider's `provider_type` is re-detected by probing the new URL

#### Scenario: Update env-sourced provider rejected
- **WHEN** an admin sends `PUT /api/llm/providers/{id}` for a provider with `source: "env"`
- **THEN** the backend returns HTTP 403

#### Scenario: Delete provider clears referencing model settings
- **WHEN** an admin deletes a provider and `llm_model` references that provider's ID
- **THEN** the `llm_model` setting is cleared (set to `{"provider_id": null, "model": ""}`)

#### Scenario: Delete default provider rejected
- **WHEN** an admin sends `DELETE /api/llm/providers/{id}` for the default provider
- **THEN** the backend returns HTTP 409

#### Scenario: Non-admin access denied
- **WHEN** a non-admin user sends any request to `/api/llm/providers`
- **THEN** the backend returns HTTP 403

### Requirement: Provider type probing
When a provider is created or its `base_url` is updated, the backend SHALL probe the URL to detect the provider type:
1. Strip `/v1` suffix from `base_url` if present, then send `GET {stripped_url}/model/info` with `Authorization: Bearer {api_key}`. If the response is HTTP 200 with a JSON body containing a `data` array, the provider type is `litellm`.
2. Otherwise, send `GET {base_url}/models` with `Authorization: Bearer {api_key}`. If the response is HTTP 200 with a JSON body containing a `data` array, the provider type is `openai_compatible`.
3. If neither probe succeeds, the provider type is `unknown`.

Probing SHALL use a 10-second timeout per request. Probe failures (network errors, non-200 responses) SHALL NOT prevent provider creation — the type defaults to `unknown`.

#### Scenario: LiteLLM detected
- **WHEN** a provider's base URL responds to `/model/info` with a valid data array
- **THEN** the provider type is set to `litellm`

#### Scenario: OpenAI-compatible detected
- **WHEN** a provider's base URL does not respond to `/model/info` but responds to `/models` with a data array
- **THEN** the provider type is set to `openai_compatible`

#### Scenario: Unknown provider
- **WHEN** neither `/model/info` nor `/models` returns a valid response
- **THEN** the provider type is set to `unknown`

#### Scenario: Probe timeout does not block creation
- **WHEN** the probe requests time out after 10 seconds
- **THEN** the provider is created with type `unknown`

### Requirement: Env var scanning at startup
On application startup, the backend SHALL scan for indexed environment variables `LLM_PROVIDER_{N}_NAME`, `LLM_PROVIDER_{N}_BASE_URL`, `LLM_PROVIDER_{N}_API_KEY` starting at N=0. For each complete set (all three vars present), the backend SHALL upsert a provider row with `source: "env"`. The provider at index 0 SHALL have `is_default: true`. Scanning SHALL stop at the first index where any of the three vars is missing. Provider type probing SHALL run for each env-sourced provider.

Env-sourced providers that no longer have corresponding env vars (from a previous startup) SHALL be deleted from the table.

#### Scenario: Two providers from env vars
- **WHEN** `LLM_PROVIDER_0_NAME=litellm`, `LLM_PROVIDER_0_BASE_URL=https://...`, `LLM_PROVIDER_0_API_KEY=sk-...`, `LLM_PROVIDER_1_NAME=openai`, `LLM_PROVIDER_1_BASE_URL=https://...`, `LLM_PROVIDER_1_API_KEY=sk-...` are set
- **THEN** two providers are upserted with `source: "env"`, the first with `is_default: true`

#### Scenario: Scanning stops at gap
- **WHEN** index 0 and 2 have all three vars but index 1 is missing `LLM_PROVIDER_1_NAME`
- **THEN** only the provider at index 0 is created

#### Scenario: Stale env-sourced providers cleaned up
- **WHEN** a previous startup created env-sourced provider "old-provider" but the current env vars do not include it
- **THEN** the "old-provider" row is deleted from the table

### Requirement: Per-provider model listing
The backend SHALL expose `GET /api/llm/providers/{id}/models` requiring the `admin` role. The endpoint SHALL return a sorted JSON array of model ID strings.

For `litellm` providers: call `AsyncOpenAI(base_url, api_key).models.list()` and return sorted model IDs. If query parameter `mode` is provided (e.g. `?mode=audio_transcription`), additionally query `{stripped_base_url}/model/info` and filter to models matching that mode.

For `openai_compatible` providers: call `AsyncOpenAI(base_url, api_key).models.list()` and return sorted model IDs (no mode filtering).

For `unknown` providers: return HTTP 404 with `{"detail": "Provider does not support model listing"}`.

#### Scenario: List models from LiteLLM provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` for a LiteLLM provider
- **THEN** the response is a sorted JSON array of model IDs from `models.list()`

#### Scenario: List transcription models from LiteLLM provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models?mode=audio_transcription` for a LiteLLM provider
- **THEN** the response is a sorted JSON array of model IDs where `model_info.mode` is `audio_transcription`

#### Scenario: List models from OpenAI-compatible provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` for an OpenAI-compatible provider
- **THEN** the response is a sorted JSON array of model IDs (no mode filtering applied)

#### Scenario: List models from unknown provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` for an unknown provider
- **THEN** the backend returns HTTP 404

#### Scenario: Provider not found
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` with a non-existent provider ID
- **THEN** the backend returns HTTP 404

### Requirement: Client pool
The backend SHALL maintain an in-memory dict of `AsyncOpenAI` clients keyed by provider UUID. The `get_client_for_provider(provider_id, session)` function SHALL return a cached client if one exists, or create a new one by reading the provider row, decrypting the API key, and instantiating `AsyncOpenAI(base_url=provider.base_url, api_key=decrypted_key)`. When a provider is updated or deleted, its cached client SHALL be evicted.

#### Scenario: Client created lazily
- **WHEN** `get_client_for_provider(uuid1)` is called for the first time
- **THEN** a new `AsyncOpenAI` client is created and cached

#### Scenario: Client reused on subsequent calls
- **WHEN** `get_client_for_provider(uuid1)` is called a second time
- **THEN** the same cached client instance is returned

#### Scenario: Client evicted on provider update
- **WHEN** a provider is updated via `PUT /api/llm/providers/{id}`
- **THEN** the cached client for that provider is removed from the pool

#### Scenario: Client evicted on provider delete
- **WHEN** a provider is deleted via `DELETE /api/llm/providers/{id}`
- **THEN** the cached client for that provider is removed from the pool

### Requirement: Set default provider
The backend SHALL expose `PUT /api/llm/providers/{id}/default` requiring the `admin` role. The endpoint SHALL set `is_default: true` on the specified provider and `is_default: false` on all other providers. Env-sourced providers SHALL be eligible as default. The endpoint SHALL return the updated provider.

#### Scenario: Change default provider
- **WHEN** an admin sends `PUT /api/llm/providers/{id}/default` for a non-default provider
- **THEN** that provider becomes the default and the previous default loses its flag

#### Scenario: Provider not found
- **WHEN** an admin sends `PUT /api/llm/providers/{id}/default` with a non-existent ID
- **THEN** the backend returns HTTP 404
