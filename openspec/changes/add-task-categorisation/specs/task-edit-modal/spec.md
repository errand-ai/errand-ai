## MODIFIED Requirements

### Requirement: Task edit modal displays editable fields
The task edit modal SHALL be implemented as a `<dialog>` element. It SHALL display editable fields for the task title, description, status, tags, category, execute_at, repeat_interval, and repeat_until, along with Save, Cancel, and Delete buttons.

#### Scenario: Modal shows current task data
- **WHEN** the edit modal opens for a task with title "Process report", description "Generate the quarterly report from the data warehouse", status "running", tags "urgent", category "immediate", execute_at "2026-02-10T14:00:00Z", and repeat_interval null
- **THEN** the title input contains "Process report", the description textarea contains the description text, the status selector shows "Running", the tag "urgent" is displayed, the category selector shows "Immediate", the execute_at datetime picker shows the datetime in local time, and the repeat_interval field is empty

#### Scenario: Status selector shows all valid statuses
- **WHEN** the edit modal is open
- **THEN** the status field SHALL present six statuses as selectable options: New, Scheduled, Pending, Running, Review, Completed

#### Scenario: Category selector shows all valid categories
- **WHEN** the edit modal is open
- **THEN** the category field SHALL present three categories as selectable options: Immediate, Scheduled, Repeating

#### Scenario: Execute_at uses datetime picker
- **WHEN** the edit modal is open
- **THEN** the execute_at field SHALL be a native datetime-local input displaying the value in the user's local time zone

#### Scenario: Execute_at field editable
- **WHEN** the user modifies the execute_at datetime via the picker and clicks Save
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with the updated execute_at value in UTC ISO 8601 format

#### Scenario: Repeat_interval with guided input
- **WHEN** the edit modal is open for a task with category "repeating"
- **THEN** the repeat_interval field is visible with helper text showing accepted formats: simple intervals (15m, 1h, 1d, 1w) and crontab expressions (e.g. "0 9 * * MON-FRI")

#### Scenario: Repeat_interval quick-select buttons
- **WHEN** the edit modal is open for a task with category "repeating"
- **THEN** quick-select buttons for common intervals (15m, 1h, 1d, 1w) are displayed and clicking one populates the repeat_interval input

#### Scenario: Repeat_interval field editable
- **WHEN** the user modifies the repeat_interval and clicks Save
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with the updated repeat_interval value

#### Scenario: Repeat_interval hidden for non-repeating tasks
- **WHEN** the edit modal is open for a task with category "immediate" or "scheduled"
- **THEN** the repeat_interval field and quick-select buttons are hidden

#### Scenario: Repeat_until uses datetime picker
- **WHEN** the edit modal is open for a task with category "repeating"
- **THEN** a "Repeat until" field is visible with a native datetime-local input

#### Scenario: Repeat_until field editable
- **WHEN** the user sets a repeat_until datetime and clicks Save
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with the updated repeat_until value in UTC ISO 8601 format

#### Scenario: Repeat_until hidden for non-repeating tasks
- **WHEN** the edit modal is open for a task with category "immediate" or "scheduled"
- **THEN** the repeat_until field is hidden

#### Scenario: Delete button in modal
- **WHEN** the edit modal is open
- **THEN** a "Delete" button is displayed, styled as a danger action, separate from Save and Cancel

#### Scenario: Delete button shows confirmation
- **WHEN** the user clicks the Delete button in the edit modal
- **THEN** a confirmation dialog appears asking "Are you sure you want to delete this task?"

#### Scenario: Confirm delete in modal
- **WHEN** the user confirms the deletion
- **THEN** the frontend sends `DELETE /api/tasks/{id}`, the modal closes, and the task is removed from the board

#### Scenario: Cancel delete in modal
- **WHEN** the user cancels the deletion
- **THEN** the modal remains open and no API call is made
