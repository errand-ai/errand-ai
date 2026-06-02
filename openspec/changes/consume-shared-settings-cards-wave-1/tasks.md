## Tasks

### Backend (capabilities)

- [ ] Locate the `/api/capabilities` handler (likely `errand/main.py` or `errand/capabilities.py`).
- [ ] Add the five always-on Wave 1 keys: `system_prompt`, `mcp_servers`, `skills_git_repo`, `task_management`, `telemetry`.
- [ ] Add conditional advertisement for `cloud_storage`, `jira`, `litellm_mcp` based on existing runtime detection.
- [ ] Add a backend test verifying always-on keys are present and conditional keys gate correctly.

### Frontend dependency bump

- [ ] Update `frontend/package.json` to require `@errand-ai/ui-components@^0.7.0` (or whatever version the library publishes).
- [ ] Run `npm install` in `frontend/`. Commit `package-lock.json`.

### Page migration

- [ ] Modify `frontend/src/pages/SettingsPage.vue` — replace the body with `<SettingsShell :sections="sections"><router-view /></SettingsShell>`. Define the `sections` array (8 entries with `id`, `label`, optional `requiresCapability`/`badge`).
- [ ] Delete `frontend/src/components/settings/SettingsSectionPicker.vue` (Phase 0 component).
- [ ] Modify `AgentConfigurationPage.vue` — import `SystemPromptCard`, `McpServersCard`, `SkillsRepoCard`, `LitellmMcpCard` from `@errand-ai/ui-components`. Replace local component usage. Keep `<SkillsSettings>` (Wave 3).
- [ ] Modify `TaskManagementPage.vue` — import `TaskManagementCard`, `TelemetryCard`. Replace usage. Keep `LlmProviderSettings` and `LlmModelSettings` (Wave 2).
- [ ] Modify `IntegrationsPage.vue` — import `CloudStorageCard`, `JiraCredentialCard` (rename if needed to avoid name collision with local file). Replace usage. Keep `GoogleWorkspaceIntegration` and `PlatformSettings` (Wave 2).

### Removals

- [ ] Delete `frontend/src/components/settings/SystemPromptSettings.vue`.
- [ ] Delete `frontend/src/components/settings/McpServerConfigSettings.vue`.
- [ ] Delete `frontend/src/components/settings/SkillsRepoSettings.vue`.
- [ ] Delete `frontend/src/components/settings/TaskManagementSettings.vue`.
- [ ] Delete `frontend/src/components/settings/TelemetrySettings.vue`.
- [ ] Delete `frontend/src/components/settings/CloudStorageIntegration.vue`.
- [ ] Delete `frontend/src/components/settings/JiraCredentialCard.vue`.
- [ ] Delete `frontend/src/components/settings/LitellmMcpSettings.vue`.
- [ ] Delete the corresponding tests under `frontend/src/components/settings/__tests__/` for the removed components.

### Tests

- [ ] Add render tests for `AgentConfigurationPage`, `TaskManagementPage`, `IntegrationsPage` verifying library cards mount.
- [ ] Add a `SettingsPage.vue` integration test verifying `<SettingsShell>` mounts and capability-gated cards hide when their capability is absent (mock `useCapabilities`).
- [ ] Update or remove tests that referenced the deleted local components.

### Verification

- [ ] Run `npm run build` (frontend) and `pytest` (backend) — both green.
- [ ] Smoke test locally with `docker compose -f testing/docker-compose.yml up --build`.
- [ ] Verify Settings on a 375px viewport: shell picker visible, content fills width.
- [ ] Verify capability gating works: temporarily flip a capability off and confirm the card disappears.

### Versioning

- [ ] Bump `VERSION` minor (e.g. 0.69.x → 0.70.0) — additive frontend changes plus capability advertisement.
