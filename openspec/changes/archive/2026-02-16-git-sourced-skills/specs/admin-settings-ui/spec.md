## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL display a heading "Settings" and organise its sections into three labelled groups. The **"Agent Configuration"** group SHALL contain "System Prompt", "Skills", "Skills Repository", and "LLM Models" sections (in that order). The **"Task Management"** group SHALL contain "Task Archiving", "Task Runner", and "Timezone" sections. The **"Integrations & Security"** group SHALL contain "MCP API Key", "Git SSH Key", and "MCP Server Configuration" sections. Each group SHALL have a visible group header label. The "Skills" section SHALL be always visible (not collapsible). The "MCP Server Configuration" section SHALL remain collapsible.

#### Scenario: Settings page renders grouped sections with Skills Repository
- **WHEN** an admin views the Settings page
- **THEN** the page displays a "Settings" heading followed by three groups: "Agent Configuration" (containing System Prompt, Skills, Skills Repository, LLM Models), "Task Management" (containing Task Archiving, Task Runner, Timezone), and "Integrations & Security" (containing MCP API Key, Git SSH Key, MCP Server Configuration)

#### Scenario: Skills Repository section positioned after Skills
- **WHEN** an admin views the Agent Configuration group
- **THEN** the "Skills Repository" section appears after the "Skills" section and before "LLM Models"

## ADDED Requirements

### Requirement: Skills Repository configuration section
The Settings page SHALL display a "Skills Repository" section in the Agent Configuration group. The section SHALL contain three input fields: a text input labelled "Repository URL" for the git clone URL, a text input labelled "Branch" with placeholder "default" for the optional branch name, and a text input labelled "Skills Path" with placeholder "/" for the optional base path within the repository. A "Save" button SHALL send the values via `PUT /api/settings` with `{"skills_git_repo": {"url": "<value>", "branch": "<value>", "path": "<value>"}}`. Empty branch and path fields SHALL be omitted from the saved JSON (not sent as empty strings). The section SHALL load its current values from `GET /api/settings` (key `skills_git_repo`) on mount.

#### Scenario: Load existing git repo configuration
- **WHEN** the Settings page loads and `skills_git_repo` is `{"url": "git@github.com:org/skills.git", "branch": "main", "path": "skills"}`
- **THEN** the Repository URL input shows `git@github.com:org/skills.git`, the Branch input shows `main`, and the Skills Path input shows `skills`

#### Scenario: No git repo configured
- **WHEN** the Settings page loads and no `skills_git_repo` setting exists
- **THEN** all three inputs are empty with their respective placeholders

#### Scenario: Save git repo configuration
- **WHEN** the admin enters a repository URL `git@github.com:org/skills.git`, branch `main`, path `skills`, and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"skills_git_repo": {"url": "git@github.com:org/skills.git", "branch": "main", "path": "skills"}}` and displays a success indication

#### Scenario: Save with only URL
- **WHEN** the admin enters only a repository URL and leaves branch and path empty, then clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"skills_git_repo": {"url": "git@github.com:org/skills.git"}}` (branch and path omitted)

#### Scenario: Clear git repo configuration
- **WHEN** the admin clears the repository URL field and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"skills_git_repo": null}` to remove the setting
