## Purpose

Admin settings page navigation layout and sub-page structure.
## Requirements
### Requirement: Settings page layout

The Settings page SHALL use the shared `<SettingsShell>` component from `@errand-ai/ui-components` to provide section navigation and responsive layout. The shell SHALL render in router mode (`<router-view />` slot) and the eight section routes (`/settings/agent`, `/settings/tasks`, `/settings/security`, `/settings/profiles`, `/settings/integrations`, `/settings/task-generators`, `/settings/cloud`, `/settings/users`) SHALL be unchanged. Responsive navigation (sidebar at viewport widths >= 640px, dropdown picker below 640px) is provided internally by `<SettingsShell>`; no app-level responsive logic remains.

The eight settings sections and their composition SHALL be:

- **Agent Configuration** (`/settings/agent`): `<SystemPromptCard>`, `<SkillsSettings>` (local, Wave 3), `<SkillsRepoCard>`, `<McpServersCard>`, `<LitellmMcpCard>` — in that order. The LiteLLM MCP card SHALL be conditionally visible via its `litellm_mcp` capability gate.
- **Task Management** (`/settings/tasks`): `<LlmProviderSettings>` (local, Wave 2), `<LlmModelSettings>` (local, Wave 2), `<TaskManagementCard>`, `<TelemetryCard>` — in that order.
- **Security** (`/settings/security`): unchanged (`GitSshKeySettings`, `McpApiKeySettings` remain local — server-admin only).
- **Task Profiles** (`/settings/profiles`): unchanged (Wave 2).
- **Integrations** (`/settings/integrations`): `<GoogleWorkspaceIntegration>` (local, Wave 2), `<CloudStorageCard>`, `<JiraCredentialCard>` (library), `<PlatformSettings>` (local, Wave 2).
- **Task Generators** (`/settings/task-generators`): unchanged.
- **Cloud Service** (`/settings/cloud`): unchanged.
- **User Management** (`/settings/users`): unchanged.

The migrated cards (`SystemPromptCard`, `McpServersCard`, `SkillsRepoCard`, `LitellmMcpCard`, `TaskManagementCard`, `TelemetryCard`, `CloudStorageCard`, `JiraCredentialCard`) are supplied by `@errand-ai/ui-components`; the previous local equivalents and the local `SettingsSectionPicker.vue` SHALL NOT exist.

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
- **THEN** `frontend/src/components/settings/SystemPromptSettings.vue`, `McpServerConfigSettings.vue`, `SkillsRepoSettings.vue`, `TaskManagementSettings.vue`, `TelemetrySettings.vue`, `CloudStorageIntegration.vue`, `LitellmMcpSettings.vue`, the local `JiraCredentialCard.vue`, and `SettingsSectionPicker.vue` SHALL NOT exist

### Requirement: Cards own their own state

Settings cards rendered via the shared library SHALL NOT depend on `provide('settings-state', ...)` from the parent `SettingsPage`. Each card SHALL load and save its own data via `useApi()`.

The `provide('settings-state')` block in `SettingsPage.vue` MAY remain to support cards still local (Wave 2 cards) but SHALL be removed in the change that completes Wave 2.

#### Scenario: Library card loads independently
- **WHEN** `<SystemPromptCard>` mounts inside the Agent Configuration page
- **THEN** the card SHALL fetch settings via `useApi()` itself
- **AND** SHALL NOT inject any provider keyed `'settings-state'`

### Requirement: Per-role timeout inputs adjacent to model selectors
The Task Management page's "LLM Models" section SHALL render three model groups — "Title generation", "Default task processing", and "Transcription" — and each group SHALL include both its model selector and a timeout input rendered immediately below the selector. Each timeout input SHALL be a number input with `min=1`, integer step, and a "seconds" suffix label. Each input SHALL bind to its respective settings key:

| Group | Settings key |
|---|---|
| Title generation | `title_generation_timeout` |
| Default task processing | `task_processing_timeout` |
| Transcription | `transcription_timeout` |

When the page is saved, the frontend SHALL include all three timeout values in the `PUT /api/settings` payload alongside the model selections. The previous standalone generic "LLM Timeout" input SHALL be removed from the page.

#### Scenario: Three timeout inputs render adjacent to model selectors
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** the "LLM Models" section displays three groups, each with a model selector and a timeout input directly below it

#### Scenario: Saving sends all three timeout values
- **WHEN** an admin sets the title timeout to 20, the task processing timeout to 180, and the transcription timeout to 45 and clicks Save
- **THEN** the frontend sends `PUT /api/settings` with `title_generation_timeout: 20`, `task_processing_timeout: 180`, and `transcription_timeout: 45`

#### Scenario: Defaults shown when no settings exist
- **WHEN** an admin loads the page and none of the three timeout settings exist in the database
- **THEN** all three timeout inputs display `30`

#### Scenario: Legacy generic input removed
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** no standalone "LLM Timeout" input exists outside the per-model groups

