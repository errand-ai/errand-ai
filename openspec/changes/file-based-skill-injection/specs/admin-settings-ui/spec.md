## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL display a heading "Settings" and organise its sections into three labelled groups. The **"Agent Configuration"** group SHALL contain "System Prompt", "Skills", and "LLM Models" sections (in that order). The **"Task Management"** group SHALL contain "Task Archiving", "Task Runner", and "Timezone" sections. The **"Integrations & Security"** group SHALL contain "MCP API Key", "Git SSH Key", and "MCP Server Configuration" sections. Each group SHALL have a visible group header label. The "Skills" section SHALL be always visible (not collapsible). The "MCP Server Configuration" section SHALL remain collapsible.

#### Scenario: Settings page renders grouped sections
- **WHEN** an admin views the Settings page
- **THEN** the page displays a "Settings" heading followed by three groups: "Agent Configuration" (containing System Prompt, Skills, LLM Models), "Task Management" (containing Task Archiving, Task Runner, Timezone), and "Integrations & Security" (containing MCP API Key, Git SSH Key, MCP Server Configuration)

#### Scenario: Skills section is always visible
- **WHEN** an admin views the Settings page
- **THEN** the Skills section is displayed expanded without a collapse toggle

#### Scenario: Group headers are visible
- **WHEN** an admin views the Settings page
- **THEN** the labels "Agent Configuration", "Task Management", and "Integrations & Security" are visible as section group headers
