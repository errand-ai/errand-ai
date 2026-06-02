## Why

Once the shared `@errand-ai/ui-components` library exposes `<SettingsShell>` and Wave 1 cards (see `add-settings-shell-and-wave-1-cards` in the library repo), Errand UI should adopt them so:

1. Settings on small screens stop being a hand-rolled fix (Phase 0 picker becomes obsolete).
2. The same code path is exercised by both Errand UI and Errand Cloud — fewer divergence bugs.
3. Future card improvements happen once, in the library, and both apps benefit.

## What Changes

- Bump `@errand-ai/ui-components` to the version exposing `<SettingsShell>` + Wave 1 cards.
- Replace `frontend/src/pages/SettingsPage.vue` body with `<SettingsShell :sections="..."><router-view /></SettingsShell>` (router mode).
- Delete the local `SettingsSectionPicker.vue` introduced in Phase 0 (the shell now handles responsive nav internally).
- Replace local Wave 1 components with library imports inside the per-section pages:
  - `AgentConfigurationPage.vue` — replace `SystemPromptSettings`, `McpServerConfigSettings`, `SkillsRepoSettings`, `LitellmMcpSettings` with their `*Card` equivalents from the library. (`SkillsSettings` stays — that's Wave 3.)
  - `TaskManagementPage.vue` — replace `TaskManagementSettings`, `TelemetrySettings`. (`LlmProviderSettings`, `LlmModelSettings` stay — Wave 2.)
  - `IntegrationsPage.vue` — replace `CloudStorageIntegration`, `JiraCredentialCard`. (`GoogleWorkspaceIntegration`, `PlatformSettings` stay — Wave 2.)
- Delete the now-unused local components:
  - `frontend/src/components/settings/SystemPromptSettings.vue`
  - `frontend/src/components/settings/McpServerConfigSettings.vue`
  - `frontend/src/components/settings/SkillsRepoSettings.vue`
  - `frontend/src/components/settings/TaskManagementSettings.vue`
  - `frontend/src/components/settings/TelemetrySettings.vue`
  - `frontend/src/components/settings/CloudStorageIntegration.vue`
  - `frontend/src/components/settings/JiraCredentialCard.vue`
  - `frontend/src/components/settings/LitellmMcpSettings.vue`
- Remove the `provide('settings-state', ...)` block from `SettingsPage.vue` — cards now own their own state. Keep `loadSettings` only for cards still rendered locally that depend on it (Wave 2 cards still use it; revisit at end of Wave 2).
- Update `/api/capabilities` (backend) to advertise the Wave 1 capability keys: `system_prompt`, `mcp_servers`, `skills_git_repo`, `task_management`, `telemetry`, `cloud_storage`, `jira`, `litellm_mcp`. (The capability gate inside each card depends on this.)

## Capabilities

### Modified Capabilities

- `admin-settings-ui`: Settings page composes shared library components instead of local ones; mobile responsive nav now provided by `<SettingsShell>` (replacing the Phase 0 local picker).
- `capability-registration`: Backend advertises eight new capability keys for Wave 1 settings cards.

## Impact

- **Frontend**: ~8 components deleted, equivalent imports added from library. Net code reduction ~1500 lines. The Phase 0 `SettingsSectionPicker.vue` is removed.
- **Backend**: small change to `/api/capabilities` to advertise new keys. No data model changes.
- **Tests**: existing component tests for the deleted cards become obsolete; replace with shell-level integration tests verifying each section composes the right library cards. Library handles per-card test coverage.
- **Bundle**: Errand UI bundle shrinks slightly (cards now external) but library load remains the same since `@errand-ai/ui-components` is already a dependency.
- **Risk**: capability mismatch — if backend doesn't advertise a key, the card disappears. Mitigation: backend change ships in the same PR.
