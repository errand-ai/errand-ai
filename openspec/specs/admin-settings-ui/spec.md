## Purpose

Admin settings page navigation layout and sub-page structure.
## Requirements
### Requirement: Settings page layout

The Settings page SHALL use the shared `<SettingsShell>` component from `@errand-ai/ui-components` to provide section navigation and responsive layout. The shell SHALL render in router mode (`<router-view />` slot) and the eight section routes (`/settings/agent`, `/settings/tasks`, `/settings/security`, `/settings/profiles`, `/settings/integrations`, `/settings/task-generators`, `/settings/cloud`, `/settings/users`) SHALL be unchanged. Responsive navigation (sidebar at viewport widths >= 640px, dropdown picker below 640px) is provided internally by `<SettingsShell>`; no app-level responsive logic remains.

The eight settings sections and their composition SHALL be:

- **Agent Configuration** (`/settings/agent`): `<SystemPromptCard>`, `<SkillsSettings>` (local, Wave 3), `<SkillsRepoCard>`, `<McpServersCard>`, `<LitellmMcpCard>` — in that order. The LiteLLM MCP card SHALL be conditionally visible via its `litellm_mcp` capability gate.
- **Task Management** (`/settings/tasks`): `<LlmProviderCard>`, `<LlmModelCard>`, `<TaskManagementCard>`, `<TelemetryCard>` — all from `@errand-ai/ui-components`, in that order.
- **Security** (`/settings/security`): unchanged (`GitSshKeySettings`, `McpApiKeySettings` remain local — server-admin only; each self-loads its own state).
- **Task Profiles** (`/settings/profiles`): `<TaskProfileListCard>` from `@errand-ai/ui-components` (the list and add/edit modal are internal to the card); the page-local list and edit logic SHALL NOT exist.
- **Integrations** (`/settings/integrations`): `<GoogleWorkspaceCard>`, `<CloudStorageCard>`, `<JiraCredentialCard>`, `<PlatformsCard>` — all from `@errand-ai/ui-components`.
- **Task Generators** (`/settings/task-generators`): unchanged.
- **Cloud Service** (`/settings/cloud`): unchanged.
- **User Management** (`/settings/users`): unchanged.

The migrated cards — Wave 1 (`SystemPromptCard`, `McpServersCard`, `SkillsRepoCard`, `LitellmMcpCard`, `TaskManagementCard`, `TelemetryCard`, `CloudStorageCard`, `JiraCredentialCard`) and Wave 2 (`LlmProviderCard`, `LlmModelCard`, `GoogleWorkspaceCard`, `PlatformsCard`, `TaskProfileListCard`) — are supplied by `@errand-ai/ui-components`; the previous local equivalents and the local `SettingsSectionPicker.vue` SHALL NOT exist.

#### Scenario: Sidebar at sm and above
- **WHEN** an admin navigates to `/settings/*` on a viewport >= 640px
- **THEN** `<SettingsShell>` SHALL render its sidebar (no app-level responsive logic remains)

#### Scenario: Picker on mobile
- **WHEN** an admin navigates to `/settings/*` on a viewport < 640px
- **THEN** `<SettingsShell>` SHALL render its dropdown picker
- **AND** content SHALL fill the available width

#### Scenario: Wave 1 card hidden when capability missing
- **WHEN** the connected server does not advertise the `cloud_storage` capability
- **THEN** `<CloudStorageCard>` SHALL NOT render in the Integrations page

#### Scenario: Replaced cards no longer exist locally
- **WHEN** the codebase is searched
- **THEN** the Wave 1 locals `frontend/src/components/settings/SystemPromptSettings.vue`, `McpServerConfigSettings.vue`, `SkillsRepoSettings.vue`, `TaskManagementSettings.vue`, `TelemetrySettings.vue`, `CloudStorageIntegration.vue`, `LitellmMcpSettings.vue`, the local `JiraCredentialCard.vue`, and `SettingsSectionPicker.vue` SHALL NOT exist
- **AND** the Wave 2 locals `LlmProviderSettings.vue`, `LlmModelSettings.vue`, `GoogleWorkspaceIntegration.vue`, `PlatformSettings.vue`, and `PlatformCredentialForm.vue` SHALL NOT exist

#### Scenario: Wave 2 cards rendered from library
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** the page SHALL render `<LlmProviderCard>`, `<LlmModelCard>`, `<TaskManagementCard>`, `<TelemetryCard>` imported from `@errand-ai/ui-components`
- **AND** SHALL NOT render any locally-defined LLM provider or LLM model component

#### Scenario: Task Profiles uses list card with internal modal
- **WHEN** an admin navigates to `/settings/profiles`
- **THEN** the page SHALL render exactly one component: `<TaskProfileListCard>` from `@errand-ai/ui-components`
- **WHEN** the admin clicks Edit on a profile row
- **THEN** the modal SHALL open *inside* the list card (not at page level)
- **WHEN** the viewport is < 640px
- **THEN** the modal SHALL render as a full-screen sheet with focus trapped

### Requirement: SettingsPage no longer provides shared state

The `SettingsPage.vue` SHALL NOT use `provide('settings-state', ...)`. All settings cards — library cards and the remaining server-admin locals — SHALL load and save their own state independently.

The local `loadSettings`, `saveSettings`, `extractValue`, `settingsMetadata` helpers and the per-key refs (e.g. `systemPrompt`, `mcpServersText`, `llmModel`) SHALL NOT exist in `SettingsPage.vue`; it is purely the navigation shell. The remaining local consumers (`GitSshKeySettings`, `McpApiKeySettings`, `PluginPollIntervalSettings`, and the `UserManagementPage` OIDC section) SHALL load their own state via a shared settings API helper (`useSettingsApi()`) or direct fetch.

#### Scenario: SettingsPage has no provide
- **WHEN** the codebase is searched
- **THEN** `pages/SettingsPage.vue` SHALL NOT contain `provide('settings-state'`
- **AND** SHALL NOT define refs like `systemPrompt`, `mcpServersText`, `llmModel`, etc.

#### Scenario: Server-admin cards load themselves
- **WHEN** `<GitSshKeySettings>` mounts
- **THEN** it SHALL fetch its own state via `useSettingsApi()` (or its existing direct API helper)
- **AND** SHALL NOT inject any provider keyed `'settings-state'`

#### Scenario: Load failure surfaced, not swallowed
- **WHEN** a self-loading server-admin card's initial `/api/settings` request fails (e.g. transient error or 403)
- **THEN** the card SHALL surface the load error rather than rendering its "no key generated" / blank-form empty state as if the value were genuinely absent

