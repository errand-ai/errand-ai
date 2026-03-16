## Context

The setup wizard was built when LLM configuration used flat settings keys (`openai_base_url`, `openai_api_key`) stored via `PUT /api/settings`. The backend has since migrated to a structured `LlmProvider` model with CRUD endpoints at `/api/llm/providers` and env var scanning via `LLM_PROVIDER_{N}_*`. The old settings keys no longer exist in the registry, so Step 2 of the wizard is broken — it writes to keys the backend ignores and reads from keys that don't exist.

The provider CRUD API and per-provider model listing endpoints already exist and are well-tested. This change is frontend-only.

## Goals / Non-Goals

**Goals:**
- Make the setup wizard's Step 2 (LLM provider) and Step 3 (model selection) work with the `LlmProvider` API
- Detect and display env-sourced providers as readonly (same UX, different data source)
- Save model settings as `{provider_id, model}` objects matching the current settings schema

**Non-Goals:**
- Multi-provider setup in the wizard (the wizard configures one provider — additional providers can be added later in settings)
- Changing Step 1 (admin account creation) — it works correctly
- Any backend changes — the required API endpoints already exist

## Decisions

### Step 2: Use provider API instead of settings API

**Decision**: Step 2 will use `GET /api/llm/providers` to check for existing providers and `POST /api/llm/providers` to create one, replacing `PUT /api/settings` with `openai_base_url`/`openai_api_key`.

**Rationale**: The settings keys don't exist anymore. The provider API is the canonical way to manage LLM providers. Using it keeps the wizard aligned with the settings page.

**Alternative considered**: Re-add `openai_base_url`/`openai_api_key` to the settings registry as a compatibility shim. Rejected because it would create two paths for the same data and diverge from the settings UI which already uses the provider API.

### Pre-fill from env-sourced providers

**Decision**: On entering Step 2, fetch `GET /api/llm/providers`. If an env-sourced provider exists, pre-fill the URL and API key fields as readonly (same lock icon UX). If no providers exist, show empty editable fields.

**Rationale**: This replaces the old pattern of checking `settings.openai_base_url.readonly`. The `source: "env"` field on the provider record serves the same purpose.

### Provider name field

**Decision**: Step 2 includes a Provider Name text field, defaulting to `"default"`. The field is disabled when an env-sourced provider exists (pre-filled with the env provider's name). The user can optionally customize the name before testing the connection.

**Rationale**: The name field is lightweight and avoids a magic default that users might not expect to see later in the settings page. Defaulting to `"default"` keeps it simple for users who don't care.

### Step 3: Per-provider model listing

**Decision**: Step 3 will fetch models via `GET /api/llm/providers/{id}/models` using the provider created/detected in Step 2. Model settings will be saved as `{provider_id: "<uuid>", model: "<model-id>"}` objects.

**Rationale**: The old `GET /api/llm/models` endpoint never existed. The per-provider endpoint does exist and returns the correct format.

### Test connection via provider creation

**Decision**: "Test Connection" will create the provider (or skip if env-sourced), then fetch models from it. If the provider was just created and the model fetch fails, delete the provider and show an error.

**Rationale**: The provider API already probes the base URL during creation. Fetching models validates the full connection. Cleaning up on failure avoids orphaned provider records.

**Alternative considered**: Create a dedicated `/api/llm/test-connection` endpoint. Rejected — unnecessary backend work when the existing endpoints already validate connectivity.

## Risks / Trade-offs

- **[Risk] Wizard creates a provider record before validation** → Mitigated by deleting it if model listing fails. Small window where a bad provider exists in the DB.
- **[Risk] Env-sourced provider API key is masked in GET response** → The wizard shows the masked value in the readonly field. This is acceptable since the field is non-editable anyway.
- **[Bonus fix] Router boot race condition** → While testing, discovered a pre-existing bug where navigating to `/` before auth status is fetched caused the router guard to block navigation (`authMode === null` fell through to `return false`). Fixed by allowing navigation when `authMode` is still `null`, letting App.vue redirect after boot. File: `frontend/src/router/index.ts`.
