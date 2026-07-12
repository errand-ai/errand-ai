## Tasks

### Backend (capabilities)

> **Correction after cross-repo review (errand-cloud PR #59).** The first pass added a *separate* `get_ui_capabilities()` + `/api/capabilities` route and left `get_capabilities()` untouched — which left the Cloud (whose only capability source is `get_capabilities()` via the WebSocket `register` message) still advertising kebab-case pre-Wave-1 keys, so every card self-gated away. Reworked to a single source: `get_capabilities()` now advertises the Wave 1 keys in **snake_case** (renaming `mcp-servers`→`mcp_servers`, `litellm-mcp`→`litellm_mcp`) and the `/api/capabilities` route (needed by the locally-served SPA, which can't see the WebSocket relay) is backed by that same function.

- [x] Update the capability source `get_capabilities()` in `errand/capabilities.py` (Trap 1: NOT a separate route — `get_capabilities()` feeds the errand-cloud WebSocket `register`). Add the five always-on Wave 1 keys: `system_prompt`, `mcp_servers`, `skills_git_repo`, `task_management`, `telemetry`.
- [x] Rename kebab→snake (Trap 2): `mcp-servers`→`mcp_servers`, `litellm-mcp`→`litellm_mcp` (rename, don't advertise both). Pre-Wave-1 keys (`tasks`, `settings`, `task-profiles`, `platforms`, `voice-input`) retained.
- [x] Add conditional advertisement for `cloud_storage`, `jira`, `litellm_mcp` by runtime detection. — `cloud_storage`←`ONEDRIVE_MCP_URL`, `jira`←platform registry, `litellm_mcp`←`litellm` provider row or `OPENAI_BASE_URL` (proxy-detected, so the enabling card can appear).
- [x] Back the public `GET /api/capabilities` route (for the local SPA) with `get_capabilities()` — single source of truth shared with cloud registration.
- [x] Backend tests verifying always-on keys, snake_case (no legacy kebab), and conditional gating — `test_capabilities.py` (direct) + `test_capabilities_endpoint.py` (HTTP).

### Frontend dependency bump

- [x] Update `frontend/package.json` to require `@errand-ai/ui-components@^0.7.0` (or whatever version the library publishes). — already at `^0.9.0` (exposes SettingsShell + all Wave 1 cards); no change needed.
- [x] Run `npm install` in `frontend/`. Commit `package-lock.json`. — lockfile already resolves to 0.9.0; no change needed.
- [x] Wire capabilities into `frontend/src/main.ts` (not in original plan): fetch `GET /api/capabilities` and pass a `ref<ServerCapabilities>` to `createErrandUI({ api, capabilities })` so `<CapabilityGate>`-wrapped cards (CloudStorageCard, LitellmMcpCard) gate correctly. Without this they would never render.

### Page migration

- [x] Modify `frontend/src/pages/SettingsPage.vue` — replace the body with `<SettingsShell :sections="sections"><router-view /></SettingsShell>`. Define the `sections` array (8 entries with `id`, `label`). Navigate via `@section-change` (shell emits an id; no `to` field on library `SettingsSection`). Gated `<router-view v-if="!loading" />` so Wave 2 cards (which snapshot `settings-state` on mount) still mount after load — the real shell renders its slot during loading, so this preserves the old `v-else` ordering.
- [x] Delete `frontend/src/components/settings/SettingsSectionPicker.vue` (Phase 0 component).
- [x] Modify `AgentConfigurationPage.vue` — import `SystemPromptCard`, `McpServersCard`, `SkillsRepoCard`, `LitellmMcpCard` from `@errand-ai/ui-components`. Replace local component usage. Keep `<SkillsSettings>` (Wave 3) + `MarketplacesSettings`/`PluginsSettings`/`PluginPollIntervalSettings` (not in scope). Dropped the redundant dirty-nav guard (both tracked cards migrated; the shell registry now guards them).
- [x] Modify `TaskManagementPage.vue` — import `TaskManagementCard`, `TelemetryCard`. Replace usage. Keep `LlmProviderSettings` and `LlmModelSettings` (Wave 2) + their `llmModel` dirty guard.
- [x] Modify `IntegrationsPage.vue` — import `CloudStorageCard`, `JiraCredentialCard` from the library (replaces the same-named local file). Keep `GoogleWorkspaceIntegration` and `PlatformSettings` (Wave 2).

### Removals

- [x] Delete `frontend/src/components/settings/SystemPromptSettings.vue`.
- [x] Delete `frontend/src/components/settings/McpServerConfigSettings.vue`.
- [x] Delete `frontend/src/components/settings/SkillsRepoSettings.vue`.
- [x] Delete `frontend/src/components/settings/TaskManagementSettings.vue`.
- [x] Delete `frontend/src/components/settings/TelemetrySettings.vue`.
- [x] Delete `frontend/src/components/settings/CloudStorageIntegration.vue`.
- [x] Delete `frontend/src/components/settings/JiraCredentialCard.vue`.
- [x] Delete `frontend/src/components/settings/LitellmMcpSettings.vue`.
- [x] Delete the corresponding tests for the removed components — `CloudStorageIntegration.test.ts`, `JiraCredentialCard.test.ts`, `LitellmMcpSettings.test.ts` (under `components/__tests__/`), plus `SettingsSectionPicker.spec.ts` and `SettingsPageLayout.spec.ts` (under `components/settings/__tests__/`).

### Tests

- [x] Add render tests for `AgentConfigurationPage`, `TaskManagementPage`, `IntegrationsPage` verifying library cards mount. — in `SettingsPage.test.ts` "Sub-page rendering" (asserts `*-card` stub testids for each page).
- [x] Add a `SettingsPage.vue` integration test verifying `<SettingsShell>` mounts and capability-gated cards hide when their capability is absent. — shell mount/nav/error in `SettingsPage.test.ts` (library mocked); real-plugin capability gating in `SettingsCapabilityGating.test.ts` (mocking the exported `useCapabilities` does NOT affect `CapabilityGate`'s internal ref, so the test drives a real `capabilities` ref instead).
- [x] Update or remove tests that referenced the deleted local components. — pruned `SettingsPage.test.ts` (removed System Prompt / MCP config / Skills Repository / Task Management Card / Telemetry / old sidebar+skeleton blocks; kept Skills, LLM Models, Security, Integrations coverage).

### Verification

- [x] Run `npm run build` (frontend) and `pytest` (backend) — both green. — frontend build (vue-tsc + vite) ✓; frontend vitest 332 passed; backend pytest 1693 passed.
- [ ] Smoke test locally with `docker compose -f testing/docker-compose.yml up --build`. — **manual** (not run here).
- [ ] Verify Settings on a 375px viewport: shell picker visible, content fills width. — **manual** (visual; shell owns responsive nav).
- [x] Verify capability gating works: temporarily flip a capability off and confirm the card disappears. — covered by `SettingsCapabilityGating.test.ts` (CloudStorageCard hidden without `cloud_storage`, shown with it). Manual UI spot-check still advisable.

### Versioning

- [x] Bump `VERSION` minor — 0.128.1 → 0.129.0 (additive frontend changes plus capability advertisement).
