## Tasks

### Backend (capabilities)

- [ ] Update `/api/capabilities` to advertise the four always-on Wave 2 keys (`llm_providers`, `llm_models`, `platforms`, `task_profiles`).
- [ ] Add conditional advertisement for `google_workspace` based on existing detection.
- [ ] Add backend test verifying always-on Wave 2 keys present and `google_workspace` gates correctly.

### Frontend dependency bump

- [ ] Update `frontend/package.json` to `@errand-ai/ui-components@^0.8.0`.
- [ ] Run `npm install`. Commit `package-lock.json`.

### Page migration

- [ ] Modify `TaskManagementPage.vue` — import `LlmProviderCard` and `LlmModelCard` from `@errand-ai/ui-components`. Replace local component usage. Drop the now-unused inject of `'settings-state'`.
- [ ] Modify `IntegrationsPage.vue` — import `GoogleWorkspaceCard` and `PlatformsCard`. Replace local component usage.
- [ ] Rewrite `TaskProfilesPage.vue` — replace inline list + edit logic with a single `<TaskProfileListCard />`. Remove the page's locally-defined refs, fetches, dialog refs, etc.

### Removals

- [ ] Delete `frontend/src/components/settings/LlmProviderSettings.vue`.
- [ ] Delete `frontend/src/components/settings/LlmModelSettings.vue`.
- [ ] Delete `frontend/src/components/settings/GoogleWorkspaceIntegration.vue`.
- [ ] Delete `frontend/src/components/settings/PlatformSettings.vue`.
- [ ] Delete `frontend/src/components/settings/PlatformCredentialForm.vue`.
- [ ] Delete corresponding tests in `frontend/src/components/settings/__tests__/`.

### SettingsPage cleanup

- [ ] Remove the `provide('settings-state', ...)` block from `pages/SettingsPage.vue`.
- [ ] Remove `loadSettings`, `saveSettings`, `extractValue`, `settingsMetadata`, and all per-key refs from `SettingsPage.vue`.
- [ ] Update remaining local components (`GitSshKeySettings`, `McpApiKeySettings`) to load their state independently — they currently consume `'settings-state'` via inject.
  - For each: replace inject with a local `onMounted` fetch; ensure their existing save logic still works.

### Tests

- [ ] Update or replace component tests for the migrated pages (`TaskManagementPage`, `IntegrationsPage`, `TaskProfilesPage`).
- [ ] Update tests for `GitSshKeySettings`, `McpApiKeySettings` to reflect their new self-loading behaviour.
- [ ] Add an integration test verifying `<TaskProfileListCard>` modal opens and saves on `/settings/profiles`.

### Verification

- [ ] `npm run build` (frontend) and `pytest` (backend) green.
- [ ] Local smoke test (`docker compose -f testing/docker-compose.yml up --build`):
  - All settings sections load without console errors.
  - Edit and save a Task Profile on a 375px viewport; modal renders as full-screen sheet, save succeeds.
  - Toggle a capability off (e.g. set Google Workspace disabled in the server config); confirm the card disappears.

### Versioning

- [ ] Bump `VERSION` minor (e.g. 0.71.x → 0.72.0).
