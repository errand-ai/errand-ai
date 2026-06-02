## Approach

Switch Errand UI's settings layout to the shared `<SettingsShell>` and replace eight local card components with their library equivalents. This change is coupled to the library change `add-settings-shell-and-wave-1-cards` — that must merge and publish first.

## Sequencing

1. Library change merges, package publishes (e.g. `@errand-ai/ui-components@0.7.0`).
2. This change bumps the dependency in `frontend/package.json`.
3. Backend `/api/capabilities` updated to advertise Wave 1 keys.
4. Frontend swap-in of cards + shell.
5. Delete now-unused local components.

The backend capabilities update can ship in the same commit as the frontend swap because:
- If frontend lands first without backend, capability gates hide cards (admins see nothing — bad).
- If backend lands first without frontend, no consumer cares (capabilities are ignored by the current local cards).

So: ship both together in one PR.

## Page composition after migration

```
SettingsPage.vue
└── <SettingsShell :sections="sections">
      <router-view />
    </SettingsShell>

routes/
  /settings/agent           → AgentConfigurationPage
  /settings/tasks           → TaskManagementPage
  /settings/security        → SecurityPage
  /settings/profiles        → TaskProfilesPage   ← Wave 2
  /settings/integrations    → IntegrationsPage
  /settings/task-generators → TaskGeneratorsPage ← Wave 2/3 mix
  /settings/cloud           → CloudServicePage   ← server-only
  /settings/users           → UserManagementPage ← server-only
```

Per-section pages after Wave 1:

```
AgentConfigurationPage.vue
├── <SystemPromptCard />            ← from library
├── <SkillsSettings />              ← stays local (Wave 3)
├── <SkillsRepoCard />              ← from library
├── <McpServersCard />              ← from library
└── <LitellmMcpCard />              ← from library

TaskManagementPage.vue
├── <LlmProviderSettings />         ← stays local (Wave 2)
├── <LlmModelSettings />            ← stays local (Wave 2)
├── <TaskManagementCard />          ← from library
└── <TelemetryCard />               ← from library

IntegrationsPage.vue
├── <GoogleWorkspaceIntegration />  ← stays local (Wave 2)
├── <CloudStorageCard />            ← from library
├── <JiraCredentialCard />          ← from library (note: same name as old local component — replace import)
└── <PlatformSettings />            ← stays local (Wave 2)
```

Other section pages unchanged in this phase.

## Decisions

- **Drop the Phase 0 picker.** `<SettingsShell>` provides equivalent mobile UX. Removing both the local picker and the responsive logic in `SettingsPage.vue` is part of this change.
- **Keep `provide('settings-state')`** for now. Wave 2 cards (`LlmProviderSettings`, `LlmModelSettings`, etc.) still use it via parent pages. Once Wave 2 lands, this provide can be deleted entirely.
- **JiraCredentialCard naming clash.** The local file and the library export share a name. The import swap takes care of it; just be careful that the page templates pick up the library version (verify with vue-tsc).
- **Each migrated card owns its own load/save.** Pages no longer pre-load and pass settings down for these cards. The page can still call `loadSettings()` for the still-local cards.

## Backend capability advertisement

The errand server's `/api/capabilities` endpoint currently advertises a small set (e.g. `llm`, `tasks`). Wave 1 adds:

```python
# pseudocode — actual location: errand/main.py or wherever capabilities are defined
WAVE_1_CAPS = [
    "system_prompt",
    "mcp_servers",
    "skills_git_repo",
    "task_management",
    "telemetry",
    "cloud_storage",     # only if cloud-storage feature is enabled in this server
    "jira",              # only if jira feature is enabled
    "litellm_mcp",       # only if LiteLLM proxy is detected
]
```

Capabilities for *optional* features (`cloud_storage`, `jira`, `litellm_mcp`) SHALL be advertised based on runtime detection (existing logic), not unconditionally. Capabilities for always-available features (`system_prompt`, `mcp_servers`, `skills_git_repo`, `task_management`, `telemetry`) SHALL be advertised unconditionally.

## Out of scope

- Wave 2 cards and their pages (`LlmProviderSettings`, `LlmModelSettings`, `GoogleWorkspaceIntegration`, `PlatformSettings`, `TaskProfilesPage`).
- Wave 3 cards (`SkillsSettings`, `WebhookTriggersSection`).
- `CloudServicePage`, `UserManagementPage`, `Security` cards (`GitSshKeySettings`, `McpApiKeySettings`) — server-admin only, may never move to library.
