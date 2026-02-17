## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL use a sidebar navigation layout with four sub-pages instead of a single scrolling page. The **"Agent Configuration"** sub-page (`/settings/agent`) SHALL contain "System Prompt", "Skills", "Skills Repository", and "MCP Server Configuration" sections (in that order). The **"Task Management"** sub-page (`/settings/tasks`) SHALL contain "LLM Models" and "Task Management" sections (in that order). The **"Security"** sub-page (`/settings/security`) SHALL contain "Git SSH Key" and "MCP API Key" sections. The **"Integrations"** sub-page (`/settings/integrations`) SHALL contain the platform integrations section. The "MCP Server Configuration" section SHALL remain collapsible.

Each settings section SHALL remain a separate Vue component in `frontend/src/components/settings/`:
- `SystemPromptSettings.vue`
- `SkillsSettings.vue`
- `SkillsRepoSettings.vue`
- `LlmModelSettings.vue`
- `TaskManagementSettings.vue` (consolidated: timezone, archiving, runner log level)
- `McpApiKeySettings.vue`
- `GitSshKeySettings.vue`
- `McpServerConfigSettings.vue`

Four new sub-page components SHALL exist in `frontend/src/pages/settings/`:
- `AgentConfigurationPage.vue`
- `TaskManagementPage.vue`
- `SecurityPage.vue`
- `IntegrationsPage.vue`

#### Scenario: Agent Configuration sub-page renders its sections
- **WHEN** an admin navigates to `/settings/agent`
- **THEN** the page displays System Prompt, Skills, Skills Repository, and MCP Server Configuration sections

#### Scenario: Task Management sub-page renders its sections
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** the page displays LLM Models and Task Management sections

#### Scenario: Security sub-page renders its sections
- **WHEN** an admin navigates to `/settings/security`
- **THEN** the page displays Git SSH Key and MCP API Key sections

#### Scenario: Integrations sub-page renders its sections
- **WHEN** an admin navigates to `/settings/integrations`
- **THEN** the page displays the platform integrations section

### Requirement: Task processing model selector on settings page
The Settings page SHALL display a "Default Model" dropdown (previously labelled "Task Processing Model") within the "LLM Models" section on the Task Management sub-page. The dropdown SHALL be populated by calling `GET /api/llm/models` (same endpoint as the title-generation model). The current selection SHALL be loaded from `GET /api/settings` (key `task_processing_model`). If no `task_processing_model` setting exists, the dropdown SHALL default to `claude-sonnet-4-5-20250929`. Changing the selection SHALL immediately save the choice via `PUT /api/settings` with `{"task_processing_model": "<selected>"}`.

#### Scenario: Task processing model dropdown loads with current selection
- **WHEN** the Settings page loads and the `task_processing_model` setting is "claude-sonnet-4-5-20250929"
- **THEN** the "Default Model" dropdown shows available models with "claude-sonnet-4-5-20250929" selected

#### Scenario: Task processing model dropdown with default
- **WHEN** the Settings page loads and no `task_processing_model` setting exists
- **THEN** the "Default Model" dropdown shows available models with "claude-sonnet-4-5-20250929" selected

#### Scenario: Change task processing model
- **WHEN** the admin selects a different model from the "Default Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with the new `task_processing_model` value and shows a success indication

#### Scenario: Models endpoint unavailable disables both dropdowns
- **WHEN** the Settings page loads and `GET /api/llm/models` fails
- **THEN** both model dropdowns are disabled and an error message is displayed

## MODIFIED Requirements

### Requirement: Consistent explicit save pattern
All settings sections SHALL use explicit Save buttons. The three previously auto-saving controls (LLM model dropdowns, Timezone dropdown, Task Runner Log Level dropdown) SHALL no longer auto-save on change. Instead, they SHALL require the user to click a Save button. Each section SHALL track whether its current values differ from the last-saved values. When a section has unsaved changes, it SHALL display a "Unsaved changes" indicator (`text-xs text-amber-600`) near its Save button.

The active sub-page SHALL register a `beforeunload` event listener when any child section has unsaved changes. The listener SHALL show the browser's native "Leave page?" confirmation when the user attempts to navigate away from the settings pages entirely.

#### Scenario: LLM model requires explicit save
- **WHEN** an admin changes the Default Model dropdown
- **THEN** the change is not saved until the user clicks the Save button and an "Unsaved changes" indicator appears

#### Scenario: Timezone requires explicit save
- **WHEN** an admin changes the timezone dropdown
- **THEN** the change is not saved until the user clicks the Save button

#### Scenario: Unsaved changes indicator
- **WHEN** an admin modifies any setting without saving
- **THEN** a "Unsaved changes" label appears in amber near the Save button

#### Scenario: Beforeunload guard
- **WHEN** any settings section on the active sub-page has unsaved changes and the user attempts to navigate away from settings
- **THEN** the browser shows a "Leave page?" confirmation dialog

#### Scenario: No guard when all saved
- **WHEN** all settings sections on the active sub-page have their saved values unchanged
- **THEN** navigating away does not trigger any confirmation
