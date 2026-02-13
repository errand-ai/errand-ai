## MODIFIED Requirements

### Requirement: Edit modal read-only for running tasks

_(Append to existing requirement — read-only mode)_

When the edit modal opens for a task with `status = "running"`, all form fields (title, description, tags, category, execute_at, repeat_interval, repeat_until) SHALL be rendered as read-only (disabled inputs or plain text). The "Save" and "Delete" action buttons SHALL be hidden. Only the "Close" / "Cancel" button SHALL be visible. The task runner logs section (if present) SHALL remain viewable.

#### Scenario: Running task opens in read-only mode
- **WHEN** the user opens the edit modal for a task with status "running"
- **THEN** all form fields are disabled/read-only and the Save and Delete buttons are hidden

#### Scenario: Non-running task opens in edit mode
- **WHEN** an editor opens the edit modal for a task with status "new"
- **THEN** all form fields are editable and the Save and Delete buttons are visible

#### Scenario: Runner logs visible in read-only mode
- **WHEN** the edit modal opens in read-only mode for a running task with runner_logs
- **THEN** the "Task Runner Logs" collapsible section is visible and expandable

### Requirement: Edit modal read-only for viewer users

When a user with the `viewer` role opens the edit modal, all form fields SHALL be rendered as read-only regardless of the task's status. The "Save" and "Delete" action buttons SHALL be hidden. Only the "Close" / "Cancel" button SHALL be visible. This allows viewers to inspect task details without the ability to modify them.

#### Scenario: Viewer opens edit modal for any task
- **WHEN** a viewer opens the edit modal for a task with status "new"
- **THEN** all form fields are disabled/read-only and the Save and Delete buttons are hidden

#### Scenario: Viewer opens edit modal for completed task
- **WHEN** a viewer opens the edit modal for a task with status "completed"
- **THEN** all form fields are disabled/read-only, output is viewable, and action buttons are hidden

#### Scenario: Editor opens edit modal for non-running task
- **WHEN** an editor opens the edit modal for a task with status "review"
- **THEN** all form fields are editable and action buttons are visible
