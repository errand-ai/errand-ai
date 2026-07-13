## Tasks

### Backend (capabilities)

- [x] Update `/api/capabilities` to advertise the four always-on Wave 2 keys (`llm_providers`, `llm_models`, `platforms`, `task_profiles`). — `platforms` was already advertised; added `llm_providers`, `llm_models`, `task_profiles` (snake_case) to `ALWAYS_ON_CAPABILITIES`. Kept the pre-Wave-1 kebab `task-profiles` for errand-cloud.
- [x] Add conditional advertisement for `google_workspace` based on existing detection. — Gated on `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` (same gate as `integration_routes._has_local_credentials` for the OAuth callback).
- [x] Add backend test verifying always-on Wave 2 keys present and `google_workspace` gates correctly. — `test_capabilities.py` + `test_capabilities_endpoint.py` (15 passed).

### Frontend dependency bump

- [x] Update `frontend/package.json` to `@errand-ai/ui-components@^0.8.0`. — Already satisfied: the dep is at `^0.9.0`, which exports all five Wave 2 cards (`LlmProviderCard`, `LlmModelCard`, `GoogleWorkspaceCard`, `PlatformsCard`, `TaskProfileListCard`). No downgrade needed.
- [x] Run `npm install`. Commit `package-lock.json`. — No dep change; lockfile already resolved to 0.9.0.

### Page migration

- [x] Modify `TaskManagementPage.vue` — import `LlmProviderCard` and `LlmModelCard` from `@errand-ai/ui-components`. Replace local component usage. Drop the now-unused inject of `'settings-state'`.
- [x] Modify `IntegrationsPage.vue` — import `GoogleWorkspaceCard` and `PlatformsCard`. Replace local component usage.
- [x] Rewrite `TaskProfilesPage.vue` — replace inline list + edit logic with a single `<TaskProfileListCard />`. Remove the page's locally-defined refs, fetches, dialog refs, etc.

### Removals

- [x] Delete `frontend/src/components/settings/LlmProviderSettings.vue`.
- [x] Delete `frontend/src/components/settings/LlmModelSettings.vue`.
- [x] Delete `frontend/src/components/settings/GoogleWorkspaceIntegration.vue`.
- [x] Delete `frontend/src/components/settings/PlatformSettings.vue`.
- [x] Delete `frontend/src/components/settings/PlatformCredentialForm.vue`.
- [x] Delete corresponding tests (actual path: `frontend/src/components/__tests__/` — `GoogleWorkspaceIntegration.test.ts`, `PlatformSettings.test.ts`, `PlatformCredentialForm.test.ts`; there are no local LLM component tests).

### SettingsPage cleanup

- [x] Remove the `provide('settings-state', ...)` block from `pages/SettingsPage.vue`.
- [x] Remove `loadSettings`, `saveSettings`, `extractValue`, `settingsMetadata`, and all per-key refs from `SettingsPage.vue`.
- [x] Update **all four** remaining `'settings-state'` consumers to load their state independently (the design originally named only the first two):
  - `GitSshKeySettings`, `McpApiKeySettings` (via `SecurityPage`).
  - `PluginPollIntervalSettings` (via `AgentConfigurationPage`).
  - `UserManagementPage` OIDC section (uses `settingsMetadata` + `saveSettings`).
  - Introduce a small `useSettingsApi()` composable (auth-aware GET/PUT + `extractValue`) so each self-loader shares one implementation; drop the `inject('settings-state')` from `SecurityPage`, `AgentConfigurationPage`, `UserManagementPage`.

### Tests

- [x] Update or replace component tests for the migrated pages (`TaskManagementPage`, `IntegrationsPage`, `TaskProfilesPage`). — `SettingsPage.test.ts` (dropped the deleted LLM-component sub-page block + page-level error tests; added the four Wave 2 card stubs; updated sub-page-render assertions); rewrote `TaskProfilesPage.test.ts` against the real library; extended `SettingsCapabilityGating.test.ts` with `google_workspace`/`platforms` gating and removed dead mocks for deleted files.
- [x] Update tests for `GitSshKeySettings`, `McpApiKeySettings`, `PluginPollIntervalSettings`, and `UserManagementPage` OIDC to reflect their new self-loading behaviour. — Rewrote `PluginPollIntervalSettings.test.ts` (self-load via stubbed fetch). GitSsh/McpApiKey self-loading is exercised by the passing SettingsPage "Security sub-page" tests; `UserManagementPage.test.ts` already mocks `/api/settings` fetch directly, so it exercises the OIDC self-load unchanged.
- [x] Add an integration test verifying `<TaskProfileListCard>` modal opens and saves on `/settings/profiles`. — In `TaskProfilesPage.test.ts`: Edit opens `task-profile-modal`, editing the name + submit issues `PUT /api/task-profiles/p1` and closes the modal.

### Verification

- [x] `npm run build` (frontend) and `pytest` (backend) green. — Frontend: `vue-tsc -b` clean + `vite build` OK (249 vitest tests pass). Backend: 1697 pytest passed.
- [x] Local smoke test (`docker compose -f testing/docker-compose.yml up --build`): **deploy verified this session.**
  - Stack built and booted: `testing-migrate` exited 0 (migrations applied), `testing-errand` reached `healthy`, `GET /api/health` → `{"status":"ok"}`, SPA served (`<title>Errand</title>` + container-built `/assets/index-*.js`).
  - `GET /api/capabilities` on `version 0.130.0` returned the Wave 2 keys (`llm_providers`, `llm_models`, `task_profiles`, `platforms`).
  - `google_workspace` conditional confirmed **both ways** live: absent with no `GOOGLE_CLIENT_ID/SECRET`, present when both set.
  - Task Profile modal open+save covered by `TaskProfilesPage.test.ts`; the <640px full-screen-sheet layout is library behaviour (verified in the library's own tests) — the only sub-item not visually driven here.

### Versioning

- [x] Bump `VERSION` minor. — 0.129.0 → 0.130.0.
