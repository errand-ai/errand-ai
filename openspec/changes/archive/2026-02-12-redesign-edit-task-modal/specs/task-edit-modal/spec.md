## MODIFIED Requirements

### Requirement: Task edit modal displays editable fields
The task edit modal SHALL be implemented as a `<dialog>` element with a maximum width of `max-w-3xl` (768px) and `w-full`, bounded to `max-h-[85vh]` with `overflow-y-auto`. It SHALL display editable fields for the task title, description, status, tags, category, execute_at, repeat_interval, and repeat_until, along with Save, Cancel, and Delete buttons.

The modal SHALL use a two-column CSS Grid layout (`grid grid-cols-1 md:grid-cols-2 gap-6`) at viewports 768px and above. Below 768px, the grid SHALL collapse to a single column.

**Layout assignment:**
- **Full-width (spanning both columns):** Title input at the top; error message and action buttons (Delete, Cancel, Save) at the bottom
- **Left column:** Status selector, Category selector, Execute at / Completed at, Repeat interval (conditional), Repeat until (conditional), Tags
- **Right column:** Description textarea (8 rows), Runner Logs read-only panel (conditional)

For tasks in `review` or `completed` status, the modal SHALL display the `updated_at` value with the label "Completed at" as a read-only formatted datetime, instead of the editable `execute_at` datetime picker. For all other statuses, the modal SHALL display the `execute_at` field as before.

When `task.runner_logs` is present, the modal SHALL display the logs in an always-visible read-only `<pre>` block in the right column below the description, with a "Task Runner Logs" heading label, `max-h-48` height constraint, and `overflow-auto` for scrolling. The logs SHALL NOT be wrapped in a collapsible `<details>` element.

#### Scenario: Modal shows current task data
- **WHEN** the edit modal opens for a task with title "Process report", description "Generate the quarterly report from the data warehouse", status "running", tags "urgent", category "immediate", execute_at "2026-02-10T14:00:00Z", and repeat_interval null
- **THEN** the title input contains "Process report", the description textarea contains the description text, the status selector shows "Running", the tag "urgent" is displayed, the category selector shows "Immediate", the execute_at datetime picker shows the datetime in local time, and the repeat_interval field is empty

#### Scenario: Two-column layout on desktop
- **WHEN** the edit modal opens on a viewport 768px or wider
- **THEN** the modal displays in a two-column grid layout with metadata fields (status, category, dates, tags) in the left column and content fields (description, runner logs) in the right column, with the title spanning both columns

#### Scenario: Single-column layout on narrow viewport
- **WHEN** the edit modal opens on a viewport narrower than 768px
- **THEN** all fields stack in a single column and the modal width fills the available viewport width

#### Scenario: Modal bounded to viewport height
- **WHEN** the edit modal opens and the content exceeds 85% of the viewport height
- **THEN** the modal content scrolls vertically within the `max-h-[85vh]` constraint

#### Scenario: Description textarea has expanded height
- **WHEN** the edit modal opens
- **THEN** the description textarea displays with 8 rows of height

#### Scenario: Runner logs displayed as visible panel
- **WHEN** the edit modal opens for a task with runner_logs containing log text
- **THEN** the logs are displayed in an always-visible read-only `<pre>` block below the description in the right column, with a "Task Runner Logs" heading, without a collapsible toggle

#### Scenario: Runner logs hidden when absent
- **WHEN** the edit modal opens for a task with runner_logs null
- **THEN** no runner logs section is rendered

#### Scenario: Runner logs scrollable when long
- **WHEN** the edit modal opens for a task with runner_logs content exceeding 192px in height
- **THEN** the runner logs panel shows a scrollbar and caps at `max-h-48`

#### Scenario: Review task shows completion time
- **WHEN** the edit modal opens for a task with status "review" and updated_at "2026-02-10T15:30:00Z"
- **THEN** the modal displays "Completed at" with the formatted datetime "10 Feb 2026, 15:30" (in local time) as read-only text, and does not show the execute_at datetime picker

#### Scenario: Completed task shows completion time
- **WHEN** the edit modal opens for a task with status "completed" and updated_at "2026-02-10T16:00:00Z"
- **THEN** the modal displays "Completed at" with the formatted datetime as read-only text, and does not show the execute_at datetime picker

#### Scenario: Pending task shows execute_at picker
- **WHEN** the edit modal opens for a task with status "pending"
- **THEN** the modal displays the execute_at datetime picker as usual, not the completion time

#### Scenario: Status selector shows all valid statuses
- **WHEN** the edit modal is open
- **THEN** the status field SHALL present six statuses as selectable options: New, Scheduled, Pending, Running, Review, Completed

#### Scenario: Category selector shows all valid categories
- **WHEN** the edit modal is open
- **THEN** the category field SHALL present three categories as selectable options: Immediate, Scheduled, Repeating

#### Scenario: Execute_at uses datetime picker
- **WHEN** the edit modal is open for a task not in review or completed status
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
