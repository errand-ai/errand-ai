## ADDED Requirements

### Requirement: list_tasks MCP tool
The MCP server must expose a `list_tasks` tool that returns tasks visible on the board.

#### Scenario: List all board-visible tasks (no filter)
- **WHEN** `list_tasks` is called with no parameters
- **THEN** it returns a JSON string containing all tasks that are not deleted or archived
- **AND** each entry includes `id` (UUID string), `title`, and `status`
- **AND** active tasks (non-completed) are ordered by position ASC, then created_at ASC
- **AND** completed tasks appear after active tasks, ordered by updated_at DESC

#### Scenario: Filter by status
- **WHEN** `list_tasks` is called with `status` set to a valid status (e.g. `"scheduled"`, `"completed"`)
- **THEN** it returns only tasks matching that status
- **AND** each entry includes `id`, `title`, and `status`

#### Scenario: Invalid status filter
- **WHEN** `list_tasks` is called with a `status` value that is not a valid board-visible status
- **THEN** it returns an error message listing the valid status values

#### Scenario: No tasks match
- **WHEN** `list_tasks` is called and no tasks match the query
- **THEN** it returns an empty JSON array `"[]"`
