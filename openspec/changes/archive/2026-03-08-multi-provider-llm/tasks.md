## 1. Database Model & Migration

- [x] 1.1 Create `LlmProvider` SQLAlchemy model in `errand/models.py` with columns: id (UUID), name (unique), base_url, api_key_encrypted, provider_type, is_default, source, created_at, updated_at
- [x] 1.2 Create Alembic migration for the `llm_provider` table
- [x] 1.3 Add encryption/decryption helper functions for provider API keys using existing Fernet infrastructure

## 2. Provider Type Probing

- [x] 2.1 Implement `probe_provider_type(base_url, api_key)` function that detects LiteLLM (via `/model/info`), OpenAI-compatible (via `/models`), or unknown, with 10-second timeout

## 3. Provider CRUD API

- [x] 3.1 Implement `GET /api/llm/providers` endpoint — list all providers with masked API keys, sorted by default first then name
- [x] 3.2 Implement `POST /api/llm/providers` endpoint — create provider, encrypt API key, probe type, reject duplicate names
- [x] 3.3 Implement `PUT /api/llm/providers/{id}` endpoint — update provider, re-probe if URL changed, reject env-sourced providers
- [x] 3.4 Implement `DELETE /api/llm/providers/{id}` endpoint — delete provider, clear referencing model settings, reject default/env-sourced
- [x] 3.5 Implement `PUT /api/llm/providers/{id}/default` endpoint — set provider as default
- [x] 3.6 Implement `GET /api/llm/providers/{id}/models` endpoint — list models per provider (with optional `?mode=` filter for LiteLLM)

## 4. Client Pool & Provider Resolution

- [x] 4.1 Implement client pool dict and `get_client_for_provider(provider_id, session)` with lazy creation and cache invalidation
- [x] 4.2 Remove old `init_llm_client()`, `get_llm_client_with_db()`, and the global `_client` variable from `llm.py`
- [x] 4.3 Remove `openai_base_url` and `openai_api_key` entries from `settings_registry.py`

## 5. Env Var Scanning

- [x] 5.1 Implement startup function to scan `LLM_PROVIDER_{N}_*` env vars and upsert providers with `source: "env"`, index 0 as default
- [x] 5.2 Implement cleanup of stale env-sourced providers that no longer have corresponding env vars

## 6. Model Settings Migration

- [x] 6.1 Update `generate_title()` in `llm.py` to read `llm_model` as `{provider_id, model}` and resolve via client pool
- [x] 6.2 Update `transcribe_audio()` in `llm.py` to read `transcription_model` as `{provider_id, model}` and resolve via client pool
- [x] 6.3 Update transcription status endpoint to check provider existence instead of `OPENAI_BASE_URL`
- [x] 6.4 Remove `GET /api/llm/models` and `GET /api/llm/transcription-models` endpoints from `main.py`

## 7. Worker Updates

- [x] 7.1 Update worker to read `task_processing_model` as `{provider_id, model}`, resolve provider credentials, and pass `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL` to the container
- [x] 7.2 Handle missing/deleted provider: log error and mark task as failed with `{"error": "LLM provider not configured"}`

## 8. Frontend — LLM Providers Section

- [x] 8.1 Create `LlmProviderSettings.vue` component with providers table (name, base URL, type, source, actions)
- [x] 8.2 Implement "Add Provider" modal dialog with name, base URL, API key fields
- [x] 8.3 Implement "Edit Provider" modal dialog with pre-filled fields, blank API key placeholder
- [x] 8.4 Implement "Delete Provider" with confirmation dialog showing affected model settings
- [x] 8.5 Implement "Set as Default" action button
- [x] 8.6 Add env-sourced readonly badges and default provider badges

## 9. Frontend — Model Selector Updates

- [x] 9.1 Add provider API functions to `useApi.ts`: `fetchProviders()`, `createProvider()`, `updateProvider()`, `deleteProvider()`, `setDefaultProvider()`, `fetchProviderModels(id, mode?)`
- [x] 9.2 Remove old `fetchLlmModels()` and `fetchTranscriptionModels()` API functions
- [x] 9.3 Update `LlmModelSettings.vue` — add provider dropdown next to each model selector
- [x] 9.4 Implement dynamic model dropdown: fetch from provider on selection, free-text input for `unknown` type
- [x] 9.5 Update model save functions to persist `{provider_id, model}` format
- [x] 9.6 Handle cleared model settings — show empty state prompting user to reconfigure

## 10. Frontend — Page Layout

- [x] 10.1 Update `TaskManagementPage.vue` to include `LlmProviderSettings` above `LlmModelSettings`

## 11. Helm Chart

- [x] 11.1 Replace `openai` block with `llmProviders[]` array in `values.yaml`
- [x] 11.2 Update `server-deployment.yaml` template — remove `OPENAI_*` env vars, add `range` loop for `llmProviders` indexed env vars with `existingSecret` support
- [x] 11.3 Update `worker-deployment.yaml` template — same `range` loop for `llmProviders` indexed env vars

## 12. Backend Tests

- [x] 12.1 Test `LlmProvider` model CRUD operations
- [x] 12.2 Test provider CRUD API endpoints (create, list, update, delete, set default)
- [x] 12.3 Test provider type probing (mock responses for LiteLLM, OpenAI-compatible, unknown)
- [x] 12.4 Test env var scanning and stale provider cleanup
- [x] 12.5 Test client pool (lazy creation, cache hit, invalidation on update/delete)
- [x] 12.6 Test `generate_title()` with provider-scoped model setting
- [x] 12.7 Test `transcribe_audio()` with provider-scoped model setting
- [x] 12.8 Test per-provider model listing endpoint (with and without mode filter)
- [x] 12.9 Test provider deletion cascade (model settings cleared)
- [x] 12.10 Test worker provider resolution (success, missing provider, empty setting)

## 13. Frontend Tests

- [x] 13.1 Test `LlmProviderSettings.vue` — render providers table, add/edit/delete flows, env-sourced readonly state
- [x] 13.2 Test `LlmModelSettings.vue` — provider dropdown, model fetching, free-text for unknown, save as `{provider_id, model}`
- [x] 13.3 Test provider API functions in `useApi.ts`
