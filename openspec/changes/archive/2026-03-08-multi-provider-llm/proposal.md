## Why

Errand was built assuming a single LLM provider (LiteLLM proxy), requiring only one base URL and API key. Users who don't use LiteLLM — or who want to route different model roles (title generation, task processing, transcription) through different providers — have no way to configure this. We need first-class multi-provider support so users can register multiple LLM endpoints with independent credentials and assign models from specific providers.

## What Changes

- **New `llm_provider` database table** storing provider name, base URL, encrypted API key, detected provider type, default flag, and source (env vs database)
- **Provider CRUD API** at `/api/llm/providers` with create, read, update, delete endpoints; creation probes the base URL to detect provider type (LiteLLM vs OpenAI-compatible vs unknown)
- **Env var scanning at startup** reads indexed `LLM_PROVIDER_{N}_NAME`, `LLM_PROVIDER_{N}_BASE_URL`, `LLM_PROVIDER_{N}_API_KEY` variables and upserts them into the provider table with `source: "env"`; index 0 becomes the default provider
- **Model settings become provider-scoped** — `llm_model`, `task_processing_model`, and `transcription_model` stored as `{provider_id, model}` instead of flat strings
- **Per-provider model listing** via `GET /api/llm/providers/{id}/models`; LiteLLM providers also support filtered transcription model listing via `/model/info`
- **Client pool** replaces the single global `AsyncOpenAI` client — one client per provider, lazily created, invalidated on provider update/delete
- **BREAKING**: Remove `openai_base_url` and `openai_api_key` settings keys and the `OPENAI_BASE_URL` / `OPENAI_API_KEY` env vars; replace with indexed provider env vars
- **BREAKING**: Remove `GET /api/llm/models` and `GET /api/llm/transcription-models` endpoints; replaced by per-provider endpoints
- **Frontend settings page** gets a new "LLM Providers" section above "LLM Models" in Task Management, with provider table (add/edit/delete) and default provider selector; model selectors gain a provider dropdown alongside the model dropdown
- **Helm chart** replaces `openai.baseUrl` / `openai.apiKey` values with `llmProviders[]` array; deployment template renders indexed env vars
- **Worker** uses provider-aware client lookup from the new provider table instead of the single global client

## Capabilities

### New Capabilities
- `llm-providers`: Provider entity management — CRUD, env var scanning, provider type probing, client pool, encrypted credential storage
- `llm-provider-settings-ui`: Frontend settings UI for managing LLM providers (add/edit/delete, default selection, readonly for env-sourced)
- `llm-provider-helm`: Helm chart values and templates for multi-provider env var rendering

### Modified Capabilities
- `llm-integration`: Model settings become provider-scoped `{provider_id, model}` pairs; client resolution uses provider table instead of env vars / settings keys; remove single-client init
- `admin-settings-ui`: Task Management page layout changes — new "LLM Providers" section added above "LLM Models"; model selectors gain provider dropdown
- `transcription-api`: Transcription endpoint uses provider-scoped model setting and provider-aware client lookup; transcription model listing becomes provider-specific
- `task-worker`: Worker resolves `task_processing_model` as `{provider_id, model}` and uses provider-aware client lookup
- `helm-deployment`: Replace `openai` values block with `llmProviders[]` array; update deployment templates for indexed env vars

## Impact

- **Backend**: `errand/llm.py` (client pool, provider-aware functions), `errand/models.py` (new LlmProvider model), `errand/main.py` (new provider endpoints, remove old model endpoints), `errand/settings_registry.py` (remove openai_base_url/openai_api_key entries), `errand/worker.py` (provider-aware client lookup), new Alembic migration
- **Frontend**: New `LlmProviderSettings.vue` component, modified `LlmModelSettings.vue` (provider dropdowns), modified `TaskManagementPage.vue` (new section), updated `useApi.ts` (provider API functions)
- **Helm**: `helm/errand/values.yaml` (new `llmProviders` block), `helm/errand/templates/server-deployment.yaml` and `worker-deployment.yaml` (indexed env var rendering)
- **Tests**: New provider CRUD tests, updated LLM integration tests, updated worker tests, new frontend component tests
- **Breaking**: Existing `OPENAI_BASE_URL`/`OPENAI_API_KEY` env vars and `openai_base_url`/`openai_api_key` DB settings no longer work — must migrate to indexed provider format
