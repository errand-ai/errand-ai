## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL use a sidebar navigation layout with six sub-pages. The **"Agent Configuration"** sub-page (`/settings/agent`) SHALL contain "System Prompt", "Skills", "Skills Repository", and "MCP Server Configuration" sections (in that order). The **"Task Management"** sub-page (`/settings/tasks`) SHALL contain "LLM Models" and "Task Management" sections (in that order). The **"Task Profiles"** sub-page (`/settings/profiles`) SHALL contain the task profile management interface. The **"Security"** sub-page (`/settings/security`) SHALL contain "Git SSH Key" and "MCP API Key" sections. The **"Integrations"** sub-page (`/settings/integrations`) SHALL contain the platform integrations section followed by the LiteLLM MCP Servers section (conditionally visible). The **"User Management"** sub-page (`/settings/users`) SHALL contain authentication mode and local admin account sections. The "MCP Server Configuration" section SHALL remain collapsible.

Each settings section SHALL remain a separate Vue component in `frontend/src/components/settings/`.

Five sub-page components SHALL exist in `frontend/src/pages/settings/`:
- `AgentConfigurationPage.vue`
- `TaskManagementPage.vue`
- `TaskProfilesPage.vue` (new)
- `SecurityPage.vue`
- `IntegrationsPage.vue`

#### Scenario: Settings sidebar shows six items
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the sidebar displays six links including "Task Profiles"

#### Scenario: Task Profiles sub-page renders profile management
- **WHEN** an admin navigates to `/settings/profiles`
- **THEN** the page displays the task profile list with add, edit, and delete capabilities
