## MODIFIED Requirements

### Requirement: Skip review state for external client tasks
When a task completes with `needs_input` status and was created by an external client, the task manager SHALL move it directly to `completed` instead of `review`.

#### Scenario: External client task with needs_input
- **WHEN** a task finishes with `parsed.status == "needs_input"`
- **AND** the task's `created_by` is not a known internal source (`"system"`, `"mcp"`, an email address, or `"email_poller"`)
- **THEN** the task SHALL move to `completed` status (not `review`)
- **AND** the task's output and questions SHALL still be stored

#### Scenario: Internal task with needs_input (unchanged)
- **WHEN** a task finishes with `parsed.status == "needs_input"`
- **AND** the task's `created_by` is a known internal source (e.g. `"mcp"`, `"system"`, a user email)
- **THEN** the task SHALL move to `review` status as before (backward compatible)

#### Scenario: Completed task (unchanged)
- **WHEN** a task finishes with `parsed.status == "completed"`
- **THEN** the task SHALL move to `completed` status regardless of `created_by`
