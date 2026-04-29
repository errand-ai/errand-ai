## Why

The current `llm_timeout` setting is misleading: the Settings UI presents it as a generic "LLM timeout", but in fact it is consumed only by `errand/llm.py:generate_title()` (i.e. the **title generation** model). It does not apply to the default task-processing model, the transcription model, or the LLM call inside the task-runner. Users tuning the setting expect to influence task-runner LLM calls and are surprised when they don't.

Compounding this, task profiles let admins override `model`, `reasoning_effort`, and `max_turns`, but offer no way to override timeout — even though different models (e.g. local LM Studio with cold-load latency) have very different latency profiles.

## What Changes

- Rename and re-scope the existing `llm_timeout` setting so it is unambiguously tied to the **title generation** model. **BREAKING** for the settings JSON schema (key rename) and the Settings UI layout (control moves next to the title-generation model selector).
- Add an explicit timeout setting for the **default task-processing model** (used as the fallback for tasks without a profile or where the profile inherits).
- Add an explicit timeout setting for the **transcription model**.
- Update the Settings UI so each timeout input sits adjacent to its associated model selector (title, default, transcription) — three clearly paired controls instead of one generic field.
- Extend `TaskProfile` with a nullable `llm_timeout` column (seconds, integer). When `null`, the profile inherits the default-model timeout; when set, it overrides it.
- Update the task profile editor UI to expose timeout alongside `reasoning_effort` and `max_turns`, with the same inherit-or-override pattern.
- Plumb the resolved per-task timeout from the task manager into the task-runner via a new env var, and apply it when constructing the `AsyncOpenAI` client in `task-runner/main.py` (currently the SDK default ~600s, never honouring user config).
- Migrate existing `llm_timeout` DB rows to the renamed key during schema migration so existing deployments are not silently reset to defaults.

## Capabilities

### New Capabilities

_None._ All changes refine existing capabilities.

### Modified Capabilities

- `llm-integration`: rename `llm_timeout` to a title-generation-specific key, add explicit settings for default-model and transcription-model timeouts, and document task-runner timeout propagation.
- `admin-settings-ui`: relocate the title-generation timeout next to its model selector and add timeout inputs adjacent to the default and transcription model selectors.
- `task-profile-model`: add a nullable `llm_timeout` column to `task_profiles` and accept it on create/update endpoints with validation (positive integer when set).
- `task-profile-settings-ui`: expose the new timeout field in the profile editor with inherit (null) / override (positive integer) semantics, alongside `reasoning_effort` and `max_turns`.
- `task-profile-worker-resolution`: resolve the effective timeout (profile override → default-model timeout → built-in default) and pass it to the task-runner so the LLM client honours it.

## Impact

- **Backend**: `errand/llm.py` (timeout helper renamed/split per model), `errand/settings_registry.py` (new keys), `errand/task_manager.py` (resolve + propagate timeout to runner env), `errand/models.py` (new column on `TaskProfile`), task profile API routes (validation + serialization).
- **Database migration**: new Alembic migration adding `task_profiles.llm_timeout`, plus a data migration renaming the existing `llm_timeout` settings row to its new title-generation-specific key.
- **Task-runner**: `task-runner/main.py` reads the new env var and constructs `AsyncOpenAI(..., timeout=...)`.
- **Frontend**: `SettingsPage.vue` / `LlmModelSettings.vue` (relocate and add timeout inputs), task profile editor component (add timeout field with inherit/override toggle).
- **Specs**: Five existing specs updated as listed above.
- **Tests**: backend tests for new settings keys + profile column + task-manager env propagation; frontend tests for the relocated UI controls and profile editor; task-runner tests for the timeout env var being honoured.
- **Docs**: `CLAUDE.md` "Task Processing (TaskManager)" section to mention runner-side LLM timeout env var.
- **No external API impact** beyond the renamed settings key, which is internal to this project.
