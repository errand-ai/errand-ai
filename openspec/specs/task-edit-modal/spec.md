## ADDED Requirements

### Requirement: Task runner logs section in edit modal
The task edit modal SHALL display a collapsible "Task Runner Logs" section below the action buttons. The section SHALL only be visible when the task's `runner_logs` field is non-null. The section SHALL use a `<details>` / `<summary>` HTML element, collapsed by default, with the summary text "Task Runner Logs". When expanded, the section SHALL display the `runner_logs` content in a read-only `<pre>` block with monospace font, horizontal and vertical scroll overflow, and a maximum height of 16rem (matching Tailwind `max-h-64`). The section SHALL be styled with a muted background (`bg-gray-50`) and rounded border consistent with the modal's design.

#### Scenario: Logs section visible after task processing
- **WHEN** the edit modal opens for a task with `runner_logs` containing "2026-02-10 14:00:01 INFO Starting agent execution\n2026-02-10 14:00:05 INFO Connected to MCP server"
- **THEN** a collapsible "Task Runner Logs" section is visible below the action buttons, collapsed by default

#### Scenario: Logs section hidden for unprocessed task
- **WHEN** the edit modal opens for a task with `runner_logs` null
- **THEN** no "Task Runner Logs" section is displayed

#### Scenario: Expanded logs show monospace content
- **WHEN** the user expands the "Task Runner Logs" section
- **THEN** the logs are displayed in a read-only monospace `<pre>` block with scrollable overflow and a maximum height of 16rem

#### Scenario: Large logs are scrollable
- **WHEN** the task has `runner_logs` exceeding the visible area of the pre block
- **THEN** the log area is scrollable both vertically and horizontally without growing beyond the maximum height
