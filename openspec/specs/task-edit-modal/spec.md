## Purpose

Modal dialog for editing task fields — title, description, status, tags, category, timing, and profile — with responsive two-column layout.

## Requirements

### Requirement: Task edit modal displays editable fields

The task edit modal SHALL be implemented as a `<dialog>` element with a maximum width of `max-w-3xl` (768px) and `w-full`, bounded to `max-h-[85vh]` with `overflow-y-auto`. It SHALL display editable fields for the task title, description, status, tags, category, execute_at, repeat_interval, and repeat_until, along with Save, Cancel, and Delete buttons.

The modal SHALL use a two-column CSS Grid layout (`grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-6`) at viewports 768px and above, producing an approximate 35:65 column ratio. Below 768px, the grid SHALL collapse to a single column.

**Layout assignment:**
- **Full-width (spanning both columns):** Title input at the top; error message and action buttons (Delete, Cancel, Save) at the bottom
- **Left column:** Status selector, Category selector, Execute at / Completed at, Repeat interval (conditional), Repeat until (conditional), Tags
- **Right column:** Description textarea (stretches to fill the full height of the right column, minimum 8 rows)

The right column SHALL use a flex column layout (`flex flex-col`) so the description textarea grows to fill the available vertical space, with a minimum height equivalent to 8 rows of text.

For tasks in `review` or `completed` status, the modal SHALL display the `updated_at` value with the label "Completed at" as a read-only formatted datetime, instead of the editable `execute_at` datetime picker. For all other statuses, the modal SHALL display the `execute_at` field as before.

The modal SHALL NOT display task runner logs. Runner logs are viewed via the `TaskLogModal` component, accessed from the task card's "View Logs" button.

When the edit modal opens for a task with `status = "running"` or `status = "completed"`, all form fields (title, description, status, tags, category, execute_at, repeat_interval, repeat_until) SHALL be rendered as read-only (disabled inputs or plain text). The "Save" and "Delete" action buttons SHALL be hidden. Only the "Close" / "Cancel" button SHALL be visible.

#### Scenario: Modal shows current task data

- **WHEN** the edit modal opens for a task with title "Process report", description "Generate the quarterly report from the data warehouse", status "running", tags "urgent", category "immediate", execute_at "2026-02-10T14:00:00Z", and repeat_interval null
- **THEN** the title input contains "Process report", the description textarea contains the description text, the status selector shows "Running", the tag "urgent" is displayed, the category selector shows "Immediate", the execute_at datetime picker shows the datetime in local time, and the repeat_interval field is empty

#### Scenario: Two-column layout on desktop with 35:65 ratio

- **WHEN** the edit modal opens on a viewport 768px or wider
- **THEN** the modal displays in a two-column grid layout with approximately 35:65 ratio, metadata fields (status, category, dates, tags) in the left column, and the description textarea filling the full height of the right column, with the title spanning both columns at the top

#### Scenario: Single-column layout on narrow viewport

- **WHEN** the edit modal opens on a viewport narrower than 768px
- **THEN** all fields stack in a single column and the modal width fills the available viewport width

#### Scenario: Modal bounded to viewport height

- **WHEN** the edit modal opens and the content exceeds 85% of the viewport height
- **THEN** the modal content scrolls vertically within the `max-h-[85vh]` constraint

#### Scenario: Description textarea fills right column height

- **WHEN** the edit modal opens on a viewport 768px or wider
- **THEN** the description textarea stretches to fill the full height of the right column, with a minimum height of 8 rows

#### Scenario: Runner logs not displayed in edit modal

- **WHEN** the edit modal opens for a task with runner_logs containing newline-delimited JSON events
- **THEN** no runner logs section is rendered in the edit modal

#### Scenario: Review task shows completion time

- **WHEN** the edit modal opens for a task with status "review" and updated_at "2026-02-10T15:30:00Z"
- **THEN** the modal displays "Completed at" with the formatted datetime "10 Feb 2026, 15:30" (in local time) as read-only text, and does not show the execute_at datetime picker

#### Scenario: Completed task shows completion time

- **WHEN** the edit modal opens for a task with status "completed" and updated_at "2026-02-10T16:00:00Z"
- **THEN** the modal displays "Completed at" with the formatted datetime as read-only text, and does not show the execute_at datetime picker

#### Scenario: Completed task opens in read-only mode

- **WHEN** the user opens the edit modal for a task with status "completed"
- **THEN** all form fields are disabled/read-only and the Save and Delete buttons are hidden, only Close is visible

#### Scenario: Running task opens in read-only mode

- **WHEN** the user opens the edit modal for a task with status "running"
- **THEN** all form fields are disabled/read-only and the Save and Delete buttons are hidden

#### Scenario: Non-running non-completed task opens in edit mode

- **WHEN** an editor opens the edit modal for a task with status "pending"
- **THEN** all form fields are editable and the Save and Delete buttons are visible

#### Scenario: Pending task shows execute_at picker

- **WHEN** the edit modal opens for a task with status "pending"
- **THEN** the modal displays the execute_at datetime picker as usual, not the completion time

#### Scenario: Status selector shows all valid statuses

- **WHEN** the edit modal is open
- **THEN** the status field SHALL present five statuses as selectable options: Scheduled, Pending, Running, Review, Completed

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

- **WHEN** the edit modal is open and not in read-only mode
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
