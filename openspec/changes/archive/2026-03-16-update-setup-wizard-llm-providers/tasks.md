## 1. Step 2 — Replace settings-based LLM config with provider API

- [x] 1.1 Replace `loadLlmMetadata()` to fetch `GET /api/llm/providers` instead of `GET /api/settings`, detect env-sourced provider, pre-fill URL and masked API key, set readonly flags based on `source: "env"`
- [x] 1.2 Replace `testConnection()` to create a provider via `POST /api/llm/providers` (name: `"default"`, base_url, api_key) — skip creation if env-sourced provider exists — then fetch models from `GET /api/llm/providers/{id}/models`. On failure, delete the created provider via `DELETE /api/llm/providers/{id}`. Store the provider ID for Step 3.
- [x] 1.3 Add a provider name input field (text, defaulting to `"default"`) so the user can optionally name their provider

## 2. Step 3 — Per-provider model listing and provider-aware settings

- [x] 2.1 Replace model fetching to use `GET /api/llm/providers/{id}/models` with the provider ID from Step 2 instead of the non-existent `GET /api/llm/models`
- [x] 2.2 Update `completeSetup()` to save `llm_model` and `task_processing_model` as `{provider_id: "<uuid>", model: "<model-id>"}` objects via `PUT /api/settings`

## 3. Update spec

- [x] 3.1 Archive the delta spec changes into `openspec/specs/setup-wizard/spec.md` (updated requirements for Steps 2, 3, and the settings save behavior)

## 4. Tests

- [x] 4.1 Update `SetupWizard.test.ts` mocks and assertions: replace `PUT /api/settings` with `openai_*` keys → `POST /api/llm/providers` and `GET /api/llm/providers`, replace `GET /api/llm/models` → `GET /api/llm/providers/{id}/models`, assert model settings saved as `{provider_id, model}` objects
- [x] 4.2 Add test case: env-sourced provider detected in Step 2 — fields readonly, no POST on test connection
- [x] 4.3 Add test case: test connection failure cleans up newly created provider
