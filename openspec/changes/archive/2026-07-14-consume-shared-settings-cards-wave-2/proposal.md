## Why

After Wave 1 (`consume-shared-settings-cards-wave-1`), Errand UI still hosts seven local card components for LLM providers, LLM models, Google Workspace, Platforms, Platform credential form, and the page-local Task Profiles UI. The library's Wave 2 release (`add-wave-2-settings-cards`) provides shared replacements. Adopting them reduces local code, equalises behaviour with Errand Cloud, and (for Task Profiles) brings a mobile-friendly modal sheet — the current page-local cards have Edit/Delete buttons that clip on mobile.

## What Changes

- Bump `@errand-ai/ui-components` to the version exposing Wave 2 cards (e.g. `^0.8.0`).
- Replace local components with library imports:
  - `TaskManagementPage.vue` — replace `LlmProviderSettings` → `<LlmProviderCard>`, `LlmModelSettings` → `<LlmModelCard>`.
  - `IntegrationsPage.vue` — replace `GoogleWorkspaceIntegration` → `<GoogleWorkspaceCard>`, `PlatformSettings` → `<PlatformsCard>`.
  - `TaskProfilesPage.vue` — replace inline list/edit code with `<TaskProfileListCard>` (modal is internal to the card).
- Delete the now-unused local components:
  - `frontend/src/components/settings/LlmProviderSettings.vue`
  - `frontend/src/components/settings/LlmModelSettings.vue`
  - `frontend/src/components/settings/GoogleWorkspaceIntegration.vue`
  - `frontend/src/components/settings/PlatformSettings.vue`
  - `frontend/src/components/settings/PlatformCredentialForm.vue`
- Strip the `provide('settings-state', ...)` block from `SettingsPage.vue` — no remaining local card depends on it after Wave 2.
- Remove `loadSettings` and the orchestration refs from `SettingsPage.vue` — cards are fully self-loading.
- Update `/api/capabilities` to advertise Wave 2 keys: `llm_providers`, `llm_models`, `google_workspace`, `platforms`, `task_profiles`.

## Capabilities

### Modified Capabilities

- `admin-settings-ui`: Five more sections compose library cards instead of locals; Settings page no longer provides shared state.
- `capability-registration`: Backend advertises five new capability keys.

## Impact

- **Frontend**: ~5 component deletions plus the Task Profiles page reshape. Net code reduction ~1500-2000 lines (LLM + Platforms + Task Profiles inline logic).
- **Backend**: small change to `/api/capabilities`. No data model changes.
- **UX improvement**: Task Profile editing on mobile becomes a full-screen sheet (no more clipped Edit/Delete on cards).
- **Tests**: existing component tests for the deleted cards are removed; a small set of integration tests confirms each section composes the right library cards.
- **Versioning**: bump `VERSION` minor (e.g. 0.71.x → 0.72.0).
