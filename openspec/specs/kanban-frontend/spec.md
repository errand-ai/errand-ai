## MODIFIED Requirements

### Requirement: Task cards display summary information
Each task card SHALL display the task title and any associated tags. Tags SHALL be displayed as small pills/badges below the title. Cards SHALL NOT display the task status text. Cards SHALL have an edit button and a delete icon. Cards SHALL have `draggable="true"` to support drag-and-drop interaction. Cards in the Scheduled column SHALL additionally display the `execute_at` value as a human-readable relative time string (e.g. "in 15 minutes", "at 5:00 PM today", "tomorrow at 9:00 AM") between the title and the tags.

#### Scenario: Task card with title and tags
- **WHEN** a task exists with title "Fix auth bug" and tags "urgent" and "bug"
- **THEN** the card shows the title, two tag pills labeled "urgent" and "bug", an edit button, and a delete icon

#### Scenario: Task card with no tags
- **WHEN** a task exists with title "Process report" and no tags
- **THEN** the card shows only the title, edit button, and delete icon, with no tag pills

#### Scenario: Scheduled task card shows execute_at
- **WHEN** a task in the Scheduled column has execute_at set to a future time
- **THEN** the card displays the execution time as a relative time string between the title and tags

#### Scenario: Scheduled task card with null execute_at
- **WHEN** a task in the Scheduled column has execute_at set to null
- **THEN** the card does not display any execution time

#### Scenario: Non-scheduled task card hides execute_at
- **WHEN** a task in the Pending or Running column has an execute_at value
- **THEN** the card does not display the execution time

#### Scenario: Delete icon shows confirmation
- **WHEN** the user clicks the delete icon on a task card
- **THEN** a confirmation dialog appears asking "Delete this task?"

#### Scenario: Confirm delete removes task
- **WHEN** the user confirms the deletion in the dialog
- **THEN** the frontend sends `DELETE /api/tasks/{id}` and removes the task card from the board

#### Scenario: Cancel delete keeps task
- **WHEN** the user cancels the deletion in the dialog
- **THEN** no API call is made and the task card remains on the board
