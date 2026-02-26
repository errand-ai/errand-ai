## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL use a sidebar navigation layout with five sub-pages. The **"Agent Configuration"** sub-page (`/settings/agent`) SHALL contain "System Prompt", "Skills", "Skills Repository", and "MCP Server Configuration" sections (in that order). The **"Task Management"** sub-page (`/settings/tasks`) SHALL contain "LLM Models" and "Task Management" sections (in that order). The **"Security"** sub-page (`/settings/security`) SHALL contain "Git SSH Key" and "MCP API Key" sections. The **"Integrations"** sub-page (`/settings/integrations`) SHALL contain the platform integrations section followed by the LiteLLM MCP Servers section (conditionally visible). The **"User Management"** sub-page (`/settings/users`) SHALL contain authentication mode and local admin account sections. The "MCP Server Configuration" section SHALL remain collapsible.

Each settings section SHALL remain a separate Vue component in `frontend/src/components/settings/`:
- `SystemPromptSettings.vue`
- `SkillsSettings.vue`
- `SkillsRepoSettings.vue`
- `LlmModelSettings.vue`
- `TaskManagementSettings.vue` (consolidated: timezone, archiving, runner log level)
- `McpApiKeySettings.vue`
- `GitSshKeySettings.vue`
- `McpServerConfigSettings.vue`
- `LitellmMcpSettings.vue` (new)

Four sub-page components SHALL exist in `frontend/src/pages/settings/`:
- `AgentConfigurationPage.vue`
- `TaskManagementPage.vue`
- `SecurityPage.vue`
- `IntegrationsPage.vue`

#### Scenario: Integrations sub-page renders platform and LiteLLM sections
- **WHEN** an admin navigates to `/settings/integrations` and LiteLLM is detected
- **THEN** the page displays platform integrations followed by the LiteLLM MCP Servers section

#### Scenario: Integrations sub-page renders only platforms when no LiteLLM
- **WHEN** an admin navigates to `/settings/integrations` and LiteLLM is not detected
- **THEN** the page displays only the platform integrations section
