## ADDED Requirements

### Requirement: Each task card has an edit button
Each task card on the kanban board SHALL display an edit button. Clicking the edit button SHALL open the task edit modal for that task.

#### Scenario: Edit button visible on card
- **WHEN** a task card is rendered on the board
- **THEN** the card displays an edit button (pencil icon or similar)

#### Scenario: Clicking edit opens modal
- **WHEN** the user clicks the edit button on a task card
- **THEN** the task edit modal opens, pre-populated with the task's current title and status

### Requirement: Task edit modal displays editable fields
The task edit modal SHALL be implemented as a `<dialog>` element. It SHALL display editable fields for the task title and status, along with Save and Cancel buttons.

#### Scenario: Modal shows current task data
- **WHEN** the edit modal opens for a task with title "Process report" and status "running"
- **THEN** the title input contains "Process report" and the status selector shows "Running"

#### Scenario: Status selector shows all valid statuses
- **WHEN** the edit modal is open
- **THEN** the status field SHALL present all seven statuses as selectable options: New, Need Input, Scheduled, Pending, Running, Review, Completed

### Requirement: Save button persists changes
Clicking Save SHALL send the updated task data to `PATCH /api/tasks/{id}` and close the modal. The board SHALL reflect the updated task on the next poll or immediately after a successful response.

#### Scenario: Successful save
- **WHEN** the user changes the title to "Updated report" and clicks Save
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with `{"title": "Updated report"}`, the modal closes, and the task list reloads

#### Scenario: Save with validation error
- **WHEN** the user clears the title field and clicks Save
- **THEN** the frontend displays a validation error and does not send the request

#### Scenario: Save API failure
- **WHEN** the user clicks Save and the PATCH request returns an error
- **THEN** the modal remains open and displays an error message

### Requirement: Cancel button discards changes
Clicking Cancel SHALL close the modal without sending any API request. Any edits made in the modal SHALL be discarded.

#### Scenario: Cancel discards edits
- **WHEN** the user modifies the title and clicks Cancel
- **THEN** the modal closes and no API request is made

#### Scenario: Escape key closes modal
- **WHEN** the edit modal is open and the user presses the Escape key
- **THEN** the modal closes without saving, equivalent to clicking Cancel
