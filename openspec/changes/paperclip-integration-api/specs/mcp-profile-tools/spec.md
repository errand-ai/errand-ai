## ADDED Requirements

### Requirement: Create task with profile via MCP
The `new_task` MCP tool SHALL accept an optional `profile` parameter to assign a task profile by name.

#### Scenario: Task created with valid profile
- **WHEN** `new_task` is called with `profile="Research Agent"`
- **THEN** the tool SHALL resolve the profile name to its ID
- **THEN** the task SHALL be created with the resolved `profile_id`
- **THEN** the task SHALL go to `pending` status for immediate execution

#### Scenario: Task created without profile
- **WHEN** `new_task` is called without the `profile` parameter
- **THEN** the tool SHALL behave as it does today (LLM-based profile auto-assignment for descriptions over 5 words)

#### Scenario: Invalid profile name
- **WHEN** `new_task` is called with a `profile` that does not exist
- **THEN** the tool SHALL return an error message: `"Error: Task profile '<name>' not found."`

### Requirement: List task profiles via MCP
The MCP server SHALL provide a `list_task_profiles` tool that returns available task profiles.

#### Scenario: Profiles listed successfully
- **WHEN** `list_task_profiles` is called
- **THEN** the tool SHALL return a JSON array of objects with `name`, `description`, and `model` fields for each profile

#### Scenario: No profiles configured
- **WHEN** `list_task_profiles` is called and no profiles exist
- **THEN** the tool SHALL return an empty JSON array
