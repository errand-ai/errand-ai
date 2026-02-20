## ADDED Requirements

### Requirement: task_logs tool

The MCP server SHALL expose a `task_logs` tool that accepts a `task_id` parameter (string, UUID format). The tool SHALL query the task from the database and return the contents of the `runner_logs` field. If the task does not exist, the tool SHALL return an error message. If the task exists but has no logs (null or empty), the tool SHALL return a message indicating no logs are available.

#### Scenario: Get logs of a task with runner logs

- **WHEN** a client calls the `task_logs` tool with the UUID of a task that has `runner_logs` content
- **THEN** the tool returns the full `runner_logs` text

#### Scenario: Get logs of a task with no logs

- **WHEN** a client calls the `task_logs` tool with the UUID of a task where `runner_logs` is null or empty
- **THEN** the tool returns "(no logs available)"

#### Scenario: Get logs of a non-existent task

- **WHEN** a client calls the `task_logs` tool with a UUID that does not exist in the database
- **THEN** the tool returns "Error: Task {task_id} not found."
