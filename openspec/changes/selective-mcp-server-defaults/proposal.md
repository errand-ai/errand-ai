## Why

Extracting the settings UI into `@errand-ai/ui-components` regressed MCP server configuration in two places, and errand is still pinned to a version that carries both regressions. The Wave 1 extraction (library v0.8.0) replaced the LiteLLM MCP settings section with a card whose `dirty` was hard-coded `false` and whose `save()`/`discard()` were empty stubs, so deployment-level enable/disable of LiteLLM MCP servers cannot be persisted. The Wave 2 extraction (library v0.9.0) rebuilt the task profile editor from the design text and reproduced only the fields that text happened to name, dropping eight the server persists — including `mcp_servers` and `litellm_mcp_servers`, so a profile can no longer override the deployment default.

Together these make MCP server selection unreachable from the UI at both scopes, against requirements `task-profile-settings-ui` already specifies ("List field selection UI"). The library fixed both in v0.16.0; errand is pinned at `^0.11.0` and cannot see the fix.

## What Changes

- Bump `@errand-ai/ui-components` from `^0.11.0` to `^0.16.0` in `frontend/package.json` and refresh `package-lock.json`. This is the entire functional change — errand consumes `LitellmMcpCard` and `TaskProfileListCard` directly from the library, and `createDirectApi` builds the new option-source calls itself.
- Restored by the bump (library v0.16.0), no errand code required:
  - **LitellmMcpCard** gains real dirty tracking, a per-server toggle, and a `save()` that persists `{ litellm_mcp_servers: [...] }` — an empty selection persists `[]` rather than `null` or an omitted key, so disabling the last server is not a silent no-op. A failed save keeps the card dirty so the navigation guard still fires.
  - **TaskProfileEditModal** regains `match_rules`, `max_turns`, `reasoning_effort`, `include_git_skills`, `enabled_plugins`, `mcp_servers`, `litellm_mcp_servers` and `skill_ids`, with the three list fields on a tri-state control encoding `null`/`[]`/`[...]` as inherit/none/select.
- Add a requirement to `litellm-mcp-settings-ui` covering toggle persistence. The spec's Purpose claims "viewing and toggling" but no requirement covers the save path, which is why the stubbed card shipped unnoticed. `task-profile-settings-ui` already enumerates its side and needs no change.
- **Fix a pre-existing model-shape defect** found while verifying the restored editor (added to this change rather than a separate one, by decision during implementation). The shared editor writes `model: {provider_id, model_id}`; the profile create/update endpoints stored it raw while `task_manager` read the `model` key, so selecting a model on a profile produced `OPENAI_MODEL=""` and the runner exited with `Missing required environment variables: OPENAI_MODEL`. Fixed in two layers: mirror `model`/`model_id` on write (as `PUT /api/settings` already does for `MODEL_SETTING_KEYS`), and accept either key when resolving, which repairs already-stored profiles without a migration. Independent of the version bump — v0.11.0 wrote the same shape.
- Bump `VERSION` (minor — restores user-facing capability).

Not in scope: no schema, migration, endpoint or cloud-proxy change. Every field, endpoint and validation path the restored UI calls already exists; the only server change is the model-shape normalisation described above.

## Capabilities

### New Capabilities

None. This restores behaviour already specified.

### Modified Capabilities

- `litellm-mcp-settings-ui`: add a requirement that toggling a LiteLLM MCP server persists via the settings API, with dirty/save/discard semantics and `[]` (not `null`) for an empty selection. Existing display and fetch requirements are unchanged.
- `task-profile-model`: add a requirement that the profile create/update endpoints mirror `model` and `model_id` on write. Existing CRUD requirements are unchanged.
- `task-profile-worker-resolution`: add a requirement that the resolved model name is taken from `model` or, failing that, `model_id`. Existing inheritance requirements are unchanged.

## Impact

- **Code**: `frontend/package.json`, `frontend/package-lock.json`, `VERSION`, plus `errand/main.py` (both profile write paths) and `errand/task_manager.py` (model name resolution) for the model-shape fix. No `.vue`/`.ts` source changes — `TaskProfilesPage.vue` and `AgentConfigurationPage.vue` are thin wrappers around the library cards, and `main.ts` already passes `createDirectApi({ baseUrl: '/api', ... })`.
- **Dependency span**: v0.12.0–v0.15.0 sit between the pinned and target versions (Vite 8/Vitest 4 toolchain, Tailwind v4, vue-router v5, marked v18). Errand's frontend is already on Tailwind v4, vue-router v5, marked v18 and Vitest 4, so no peer-version churn is expected; the toolchain moves are internal to the library's own build.
- **Server endpoints consumed** (all present, unchanged): `GET /api/skills`, `GET /api/plugins`, `GET /api/worker/defaults`, `GET /api/litellm/mcp-servers`, `PUT /api/settings`, `POST|PUT /api/task-profiles`.
- **Tests**: `frontend/src/pages/__tests__/TaskProfilesPage.test.ts` and `SettingsCapabilityGating.test.ts` mount the real library components and are the most likely to need updating. Requirement-level coverage of the restored fields lives in the library's own suite (302 tests).
- **Risk**: low functional risk, concentrated in the version span rather than the feature. The failure mode to watch for is a silent one — the tri-state `null`/`[]`/`[...]` encoding is a server contract that is invisible in the UI, so an inversion would strip a task's tools without any visible error. Verify a round-trip at both scopes against a real server before merge.
