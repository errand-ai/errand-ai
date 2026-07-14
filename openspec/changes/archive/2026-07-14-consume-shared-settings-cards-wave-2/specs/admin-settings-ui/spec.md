## MODIFIED Requirements

### Requirement: Settings page layout

The Settings page composition SHALL be updated as follows after Wave 2 migration:

- **Agent Configuration** (`/settings/agent`): unchanged from Wave 1 (`<SystemPromptCard>`, `<SkillsSettings>` local, `<SkillsRepoCard>`, `<McpServersCard>`, `<LitellmMcpCard>`).
- **Task Management** (`/settings/tasks`): `<LlmProviderCard>`, `<LlmModelCard>`, `<TaskManagementCard>`, `<TelemetryCard>` — all from `@errand-ai/ui-components`.
- **Security** (`/settings/security`): unchanged (`GitSshKeySettings`, `McpApiKeySettings` remain local; server-admin only).
- **Task Profiles** (`/settings/profiles`): `<TaskProfileListCard>` from `@errand-ai/ui-components`. The page-local list and edit logic SHALL be removed.
- **Integrations** (`/settings/integrations`): `<GoogleWorkspaceCard>`, `<CloudStorageCard>`, `<JiraCredentialCard>`, `<PlatformsCard>` — all from `@errand-ai/ui-components`.
- **Task Generators** (`/settings/task-generators`): unchanged.
- **Cloud Service** (`/settings/cloud`): unchanged.
- **User Management** (`/settings/users`): unchanged.

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

#### Scenario: Replaced cards no longer exist locally
- **WHEN** the codebase is searched after this change
- **THEN** `frontend/src/components/settings/LlmProviderSettings.vue` SHALL NOT exist
- **AND** `LlmModelSettings.vue` SHALL NOT exist
- **AND** `GoogleWorkspaceIntegration.vue` SHALL NOT exist
- **AND** `PlatformSettings.vue` SHALL NOT exist
- **AND** `PlatformCredentialForm.vue` SHALL NOT exist

### Requirement: SettingsPage no longer provides shared state

After Wave 2 the `SettingsPage.vue` SHALL NOT use `provide('settings-state', ...)`. All settings cards (library and remaining server-admin locals) SHALL load their own state independently.

The local `loadSettings`, `saveSettings`, `settingsMetadata` helpers and the per-key refs (e.g. `systemPrompt`, `mcpServersText`, `llmModel`) SHALL be removed from `SettingsPage.vue`. Server-admin local components (`GitSshKeySettings`, `McpApiKeySettings`) SHALL be updated to load their own state via `useApi()` or direct fetch.

#### Scenario: SettingsPage has no provide
- **WHEN** the codebase is searched
- **THEN** `pages/SettingsPage.vue` SHALL NOT contain `provide('settings-state'`
- **AND** SHALL NOT define refs like `systemPrompt`, `mcpServersText`, `llmModel`, etc.

#### Scenario: Server-admin cards load themselves
- **WHEN** `<GitSshKeySettings>` mounts
- **THEN** it SHALL fetch its own state via `useApi()` (or its existing direct API helper)
- **AND** SHALL NOT inject any `'settings-state'` provider
