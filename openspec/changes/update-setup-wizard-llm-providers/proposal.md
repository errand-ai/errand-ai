## Why

The setup wizard (Step 2: LLM Provider Configuration) still reads and writes the legacy `openai_base_url` / `openai_api_key` settings keys, which no longer exist in the settings registry. The backend has migrated to the `LlmProvider` model with env var scanning via `LLM_PROVIDER_{N}_*` and a full CRUD API at `/api/llm/providers`. The wizard needs to be updated to use the new provider system so that first-run setup actually works.

## What Changes

- **BREAKING**: Step 2 of the setup wizard no longer reads/writes `openai_base_url` or `openai_api_key` settings
- Step 2 now creates an LLM provider via `POST /api/llm/providers` instead of `PUT /api/settings`
- Step 2 pre-fills from existing providers (e.g. env-sourced) via `GET /api/llm/providers` instead of reading settings
- Readonly detection uses `source: "env"` from the provider record instead of `settings.readonly`
- Step 3 model listing uses `GET /api/llm/providers/{id}/models` (per-provider endpoint) instead of the non-existent `GET /api/llm/models`
- Step 3 saves model settings as `{provider_id, model}` objects matching the current settings schema
- The setup-wizard spec is updated to reflect the new provider-based flow

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `setup-wizard`: Step 2 requirements change from settings-based LLM config (`openai_base_url`/`openai_api_key` via `PUT /api/settings`) to provider-based config (`POST /api/llm/providers` / `GET /api/llm/providers`). Step 3 changes to use per-provider model listing and save `{provider_id, model}` settings.

## Impact

- **Frontend**: `SetupWizard.vue` — Step 2 and Step 3 logic and API calls change
- **Frontend tests**: `SetupWizard.test.ts` — test mocks need updating for new API endpoints
- **Spec**: `openspec/specs/setup-wizard/spec.md` — requirements for Steps 2 and 3 updated
- **No backend changes needed** — the provider CRUD API and per-provider model listing already exist
