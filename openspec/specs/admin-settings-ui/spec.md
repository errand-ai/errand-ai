## MODIFIED Requirements

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
