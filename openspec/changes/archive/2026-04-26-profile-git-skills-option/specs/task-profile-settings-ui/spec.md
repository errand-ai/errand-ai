## MODIFIED Requirements

### Requirement: List field selection UI
For MCP servers, LiteLLM MCP servers, and skills, the form SHALL provide a three-state selection: "Inherit from default" (saves null), "None" (saves empty array), or "Select specific" (saves the selected items as an array). The "Select specific" option SHALL show checkboxes for available items. When the skills mode is "Select specific" or "None", the form SHALL additionally display an "Include Git Repository Skills" checkbox that controls the `include_git_skills` profile field. The checkbox SHALL default to checked. When the skills mode is "Inherit from default", the git skills checkbox SHALL be hidden.

#### Scenario: Inherit from default selected
- **WHEN** an admin selects "Inherit from default" for MCP servers
- **THEN** the profile is saved with `mcp_servers: null`

#### Scenario: None selected
- **WHEN** an admin selects "None" for MCP servers
- **THEN** the profile is saved with `mcp_servers: []`

#### Scenario: Specific items selected
- **WHEN** an admin selects "Select specific" and checks "gmail" and "errand"
- **THEN** the profile is saved with `mcp_servers: ["gmail", "errand"]`

#### Scenario: Select specific skills with git skills included
- **WHEN** an admin selects "Select specific" for skills, checks 2 managed skills, and leaves "Include Git Repository Skills" checked
- **THEN** the profile is saved with `skill_ids: ["uuid-1", "uuid-2"]` and `include_git_skills: true`

#### Scenario: Select specific skills with git skills excluded
- **WHEN** an admin selects "Select specific" for skills, checks 2 managed skills, and unchecks "Include Git Repository Skills"
- **THEN** the profile is saved with `skill_ids: ["uuid-1", "uuid-2"]` and `include_git_skills: false`

#### Scenario: Git skills checkbox hidden in inherit mode
- **WHEN** an admin selects "Inherit from default" for skills
- **THEN** the "Include Git Repository Skills" checkbox is not visible

#### Scenario: Editing profile loads git skills state
- **WHEN** an admin edits a profile with `skill_ids: ["uuid-1"]` and `include_git_skills: false`
- **THEN** the skills mode shows "Select specific", the managed skill is checked, and "Include Git Repository Skills" is unchecked
