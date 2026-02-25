## Why

The LLM title generation call in `generate_title()` has a hardcoded 5-second timeout. When using local models (e.g. via Ollama or LM Studio), the model may need to be loaded into GPU/CPU memory before it can process the first request. This cold-start can easily exceed 5 seconds, causing every initial task submission to fall back to the truncated title with a "Needs Info" tag. The timeout needs to be configurable so users running local models can set a value that accommodates model loading time.

## What Changes

- Add a new `llm_timeout` setting (stored in the DB settings table like `llm_model`)
- Read `llm_timeout` from DB in `generate_title()` instead of using the hardcoded `5.0`
- Default to `30` seconds when no setting exists (generous enough for local model cold-starts while still failing on genuinely broken connections)
- Add a timeout input field to the LLM Models settings card in the frontend
- Save the timeout value via `PUT /api/settings` alongside model settings

## Capabilities

### New Capabilities

_None_ — this modifies existing capabilities only.

### Modified Capabilities

- `llm-integration`: The `generate_title` timeout becomes configurable via a DB setting instead of hardcoded
- `admin-settings-ui`: The LLM Models settings card gains a timeout input field

## Impact

- **Backend**: `errand/llm.py` — `generate_title()` reads `llm_timeout` setting, falls back to 30s default
- **Frontend**: `LlmModelSettings.vue` — add timeout input field and save logic
- **Frontend**: `SettingsPage.vue` — plumb new `llmTimeout` state through provide/inject
- **Frontend**: `TaskManagementPage.vue` — pass new prop to LlmModelSettings
- **No migration needed**: Uses existing `settings` table (key-value store)
- **No breaking changes**: Default of 30s is more permissive than the current 5s
