## MODIFIED Requirements

### Requirement: Settings page layout

The Settings page SHALL use the shared `<SettingsShell>` component from `@errand-ai/ui-components` to provide section navigation and responsive layout. The shell SHALL render in router mode (`<router-view />` slot) and the eight section routes (`/settings/agent`, `/settings/tasks`, `/settings/security`, `/settings/profiles`, `/settings/integrations`, `/settings/task-generators`, `/settings/cloud`, `/settings/users`) SHALL be unchanged.

The locally-defined `SettingsSectionPicker.vue` (introduced in `mobile-settings-subnav-dropdown`) SHALL be removed; the shell now provides responsive nav internally.

The eight settings sections and their composition SHALL be:

- **Agent Configuration** (`/settings/agent`): `<SystemPromptCard>`, `<SkillsSettings>` (local, Wave 3), `<SkillsRepoCard>`, `<McpServersCard>`, `<LitellmMcpCard>` — in that order. The LiteLLM MCP card SHALL be conditionally visible via its `litellm_mcp` capability gate.
- **Task Management** (`/settings/tasks`): `<LlmProviderSettings>` (local, Wave 2), `<LlmModelSettings>` (local, Wave 2), `<TaskManagementCard>`, `<TelemetryCard>` — in that order.
- **Security** (`/settings/security`): unchanged in this phase (`GitSshKeySettings`, `McpApiKeySettings` remain local — server-admin only).
- **Task Profiles** (`/settings/profiles`): unchanged (Wave 2).
- **Integrations** (`/settings/integrations`): `<GoogleWorkspaceIntegration>` (local, Wave 2), `<CloudStorageCard>`, `<JiraCredentialCard>` (library), `<PlatformSettings>` (local, Wave 2).
- **Task Generators** (`/settings/task-generators`): unchanged.
- **Cloud Service** (`/settings/cloud`): unchanged.
- **User Management** (`/settings/users`): unchanged.

#### Scenario: Sidebar at sm and above
- **WHEN** an admin navigates to `/settings/*` on a viewport ≥ 640px
- **THEN** `<SettingsShell>` SHALL render its sidebar (no app-level responsive logic remains)

#### Scenario: Picker on mobile
- **WHEN** an admin navigates to `/settings/*` on a viewport < 640px
- **THEN** `<SettingsShell>` SHALL render its dropdown picker

#### Scenario: Wave 1 card hidden when capability missing
- **WHEN** the connected server does not advertise the `cloud_storage` capability
- **THEN** `<CloudStorageCard>` SHALL NOT render in the Integrations page

#### Scenario: Replaced cards no longer exist locally
- **WHEN** the codebase is searched after this change merges
- **THEN** `frontend/src/components/settings/SystemPromptSettings.vue` SHALL NOT exist
- **AND** `McpServerConfigSettings.vue` SHALL NOT exist
- **AND** `SkillsRepoSettings.vue` SHALL NOT exist
- **AND** `TaskManagementSettings.vue` SHALL NOT exist
- **AND** `TelemetrySettings.vue` SHALL NOT exist
- **AND** `CloudStorageIntegration.vue` SHALL NOT exist
- **AND** `LitellmMcpSettings.vue` SHALL NOT exist
- **AND** the local `JiraCredentialCard.vue` SHALL NOT exist (library equivalent imported instead)

### Requirement: Cards own their own state

Settings cards rendered via the shared library SHALL NOT depend on `provide('settings-state', ...)` from the parent `SettingsPage`. Each card SHALL load and save its own data via `useApi()`.

The `provide('settings-state')` block in `SettingsPage.vue` MAY remain in this phase to support cards still local (Wave 2 cards) but SHALL be removed in the change that completes Wave 2.

#### Scenario: Library card loads independently
- **WHEN** `<SystemPromptCard>` mounts inside the Agent Configuration page
- **THEN** the card SHALL fetch settings via `useApi().getSettings()` itself
- **AND** SHALL NOT inject any provider keyed `'settings-state'`
