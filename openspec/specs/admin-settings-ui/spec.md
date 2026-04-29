## Purpose

Admin settings page navigation layout and sub-page structure.
## Requirements
### Requirement: Settings page layout
The Settings page SHALL use a sidebar navigation layout with six sub-pages. The **"Agent Configuration"** sub-page (`/settings/agent`) SHALL contain "System Prompt", "Skills", "Skills Repository", "MCP Server Configuration", and "MCP Servers (via LiteLLM)" sections (in that order). The LiteLLM MCP Servers section SHALL be conditionally visible (only when the LiteLLM proxy is detected). The **"Task Management"** sub-page (`/settings/tasks`) SHALL contain "LLM Providers", "LLM Models", and "Task Management" sections (in that order). The **"Task Profiles"** sub-page (`/settings/profiles`) SHALL contain the task profile management interface. The **"Security"** sub-page (`/settings/security`) SHALL contain "Git SSH Key" and "MCP API Key" sections. The **"Integrations"** sub-page (`/settings/integrations`) SHALL contain the platform integrations section. The **"User Management"** sub-page (`/settings/users`) SHALL contain authentication mode and local admin account sections. The "MCP Server Configuration" section SHALL remain collapsible.

Each settings section SHALL remain a separate Vue component in `frontend/src/components/settings/`.

Five sub-page components SHALL exist in `frontend/src/pages/settings/`:
- `AgentConfigurationPage.vue`
- `TaskManagementPage.vue`
- `TaskProfilesPage.vue`
- `SecurityPage.vue`
- `IntegrationsPage.vue`

#### Scenario: Task Management page shows three sections
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** the page displays "LLM Providers", "LLM Models", and "Task Management" sections in that order

#### Scenario: Agent Configuration page shows five sections including LiteLLM MCP
- **WHEN** an admin navigates to `/settings/agent` and the LiteLLM proxy is detected
- **THEN** the page displays System Prompt, Skills, Skills Repository, MCP Server Configuration, and MCP Servers (via LiteLLM) sections in that order

#### Scenario: Agent Configuration page hides LiteLLM MCP when unavailable
- **WHEN** an admin navigates to `/settings/agent` and the LiteLLM proxy is not detected
- **THEN** the page displays System Prompt, Skills, Skills Repository, and MCP Server Configuration sections only

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

