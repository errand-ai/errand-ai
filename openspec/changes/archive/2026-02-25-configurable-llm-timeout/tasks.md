## 1. Backend — configurable timeout in generate_title

- [x] 1.1 Add `_get_llm_timeout` helper in `errand/llm.py` that reads the `llm_timeout` setting from DB, returning a float (default `30.0`)
- [x] 1.2 Replace the hardcoded `timeout=5.0` in `generate_title()` with the value from `_get_llm_timeout(session)`
- [x] 1.3 Add backend tests: custom timeout used when setting exists, default 30s used when no setting

## 2. Frontend — timeout input in LLM Models settings card

- [x] 2.1 Add `llmTimeout` ref to `SettingsPage.vue` state, read from settings response (default `30`), provide via inject
- [x] 2.2 Add `llmTimeout` prop/emit to `LlmModelSettings.vue`, add number input with label "LLM Timeout (seconds)" and `min="1"`, include in dirty tracking and save logic
- [x] 2.3 Pass `llmTimeout` prop through `TaskManagementPage.vue`
- [x] 2.4 Add frontend tests: timeout input renders with default, saves with model settings, dirty tracking works
