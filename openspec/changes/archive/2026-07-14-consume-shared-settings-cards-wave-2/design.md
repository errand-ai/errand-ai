## Approach

Mirror image of `consume-shared-settings-cards-wave-1`: bump dependency, swap imports, delete locals, advertise capabilities. The reshape of `TaskProfilesPage.vue` is the only meaty piece.

## Sequencing

1. Library `0.8.0` published with Wave 2 cards.
2. This change bumps the dep, advertises new capabilities, swaps imports, deletes locals.
3. Wave 1 + Wave 2 in production gives Errand UI a fully shared-card settings page (excluding server-admin-only cards, Skills, Webhook Triggers).

## Page composition after Wave 2

```
TaskManagementPage.vue
├── <LlmProviderCard />   ← from library
├── <LlmModelCard />      ← from library
├── <TaskManagementCard /> ← already migrated in Wave 1
└── <TelemetryCard />      ← already migrated in Wave 1

IntegrationsPage.vue
├── <GoogleWorkspaceCard /> ← from library
├── <CloudStorageCard />    ← already migrated in Wave 1
├── <JiraCredentialCard />  ← already migrated in Wave 1
└── <PlatformsCard />       ← from library

TaskProfilesPage.vue
└── <TaskProfileListCard />  ← from library (modal internal)
```

After Wave 2, the only local components remaining in `components/settings/` are:
- `GitSshKeySettings.vue` (server-admin only — stays local)
- `McpApiKeySettings.vue` (server-admin only — stays local)
- `SkillsSettings.vue` (Wave 3 — stays local for now)
- `WebhookTriggersSection.vue` (Wave 3 — stays local for now)

## Removing `provide('settings-state')`

After Wave 2 no *card* injects `'settings-state'`, but four **pages** still do at
implementation time — more than this design originally assumed. The full set of
consumers that must become self-loading before the provide block can be removed:

- `SecurityPage` → `GitSshKeySettings`, `McpApiKeySettings` (already planned).
- `AgentConfigurationPage` → `PluginPollIntervalSettings` (uses `pluginPollIntervalSeconds` + `saveSettings`).
- `UserManagementPage` → OIDC config section (uses `settingsMetadata` + `saveSettings`).

The spec requires `SettingsPage.vue` to contain no `provide('settings-state')`, so
all four are converted to load their own `/api/settings` state and save via a small
shared `useSettingsApi()` composable (auth-aware fetch + PUT + metadata `extractValue`).
`UserManagementPage` is out of scope for *card migration* (its OIDC UI stays local),
but removing the shared provider necessarily touches it.

Once all four self-load, the provide block, the `loadSettings()` orchestration, and
the parent-tracked refs in `SettingsPage.vue` are all deleted. What remains is just
the `<SettingsShell>` wrapper.

The error/loading state previously managed in `SettingsPage.vue` is no longer relevant at the page level — cards manage their own loading. The shell's `loading` and `error` props remain available for any future need (e.g. checking auth before any cards mount); not used in the post-Wave-2 layout.

## Backend capabilities

```
WAVE_2_CAPS = [
    "llm_providers",       # always advertised (always available)
    "llm_models",          # always advertised
    "google_workspace",    # only if Google Workspace integration enabled
    "platforms",           # always advertised (always available — list may be empty)
    "task_profiles",       # always advertised
]
```

`google_workspace` advertisement gates on existing runtime detection (likely the same flag controlling the OAuth callback registration today).

## Decisions

- **Single PR for all Wave 2 swaps.** Could split per card pair, but they're all the same shape (bump, swap, delete) and the dependency bump only needs to happen once. Risk-managed by the per-card capability gates: if one card has a bug, only that card breaks.
- **Task Profiles internal modal.** Library decision: list card owns the modal. Errand UI just renders `<TaskProfileListCard />` and the page goes from ~300 lines to one component.
- **Drop `provide('settings-state')` in this change**, not earlier. Wave 1 left it because Wave 2 cards still injected it. Now nothing does.

## Out of scope

- Wave 3 (Skills, Webhook Triggers) — separate changes with their own designs.
- Server-admin cards (Git SSH, MCP API key) — stay local indefinitely.
- `CloudServicePage`, `UserManagementPage` — server-admin only.
