## MODIFIED Requirements

### Requirement: Task cards display summary information
Each task card SHALL display the task title and any associated tags. Tags SHALL be displayed as small pills/badges below the title. Cards SHALL NOT display the task status text. Cards SHALL have an edit button and a delete icon. Cards SHALL have `draggable="true"` to support drag-and-drop interaction. Cards in the Scheduled column SHALL additionally display the `execute_at` value as a human-readable relative time string (e.g. "in 15 minutes", "at 5:00 PM today", "tomorrow at 9:00 AM") between the title and the tags. The relative time display on Scheduled column cards SHALL auto-refresh approximately every 30 seconds so the countdown stays accurate without requiring a page reload.

Cards in the Review, Completed, or Scheduled columns SHALL display a "View Output" button (eye icon) when the task has a non-null `output` field. Clicking this button SHALL open the task output viewer popup. For Scheduled column cards (failed retries), the button SHALL also be shown when `output` contains error information.

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

#### Scenario: Scheduled card countdown refreshes automatically
- **WHEN** a task in the Scheduled column displays "in 5m" and 30 seconds elapse
- **THEN** the displayed relative time updates to reflect the current remaining time without user interaction

#### Scenario: Countdown timer only active for scheduled cards
- **WHEN** a task card is displayed in a non-scheduled column (e.g. Pending, Running)
- **THEN** no periodic refresh timer is active for that card

#### Scenario: Review task card shows output button
- **WHEN** a task in the Review column has a non-null output field
- **THEN** the card displays a "View Output" button (eye icon) that opens the output viewer popup

#### Scenario: Completed task card shows output button
- **WHEN** a task in the Completed column has a non-null output field
- **THEN** the card displays a "View Output" button (eye icon) that opens the output viewer popup

#### Scenario: Scheduled retry task card shows output button
- **WHEN** a task in the Scheduled column has a non-null output field (from a failed execution)
- **THEN** the card displays a "View Output" button (eye icon) that opens the output viewer popup

#### Scenario: Task card without output hides button
- **WHEN** a task in the Review column has a null output field
- **THEN** the card does not display the "View Output" button

#### Scenario: Delete icon shows styled confirmation modal
- **WHEN** the user clicks the delete icon on a task card
- **THEN** a Tailwind-styled delete confirmation modal appears asking "Delete this task?" with the task title, a red "Delete" button, and a "Cancel" button

#### Scenario: Confirm delete removes task
- **WHEN** the user confirms the deletion in the styled modal
- **THEN** the frontend sends `DELETE /api/tasks/{id}` and removes the task card from the board

#### Scenario: Cancel delete keeps task
- **WHEN** the user cancels the deletion in the styled modal
- **THEN** no API call is made and the task card remains on the board

The delete icon on task cards SHALL NOT be displayed when the user has the `viewer` role (checked via `isViewer` from the auth store). The delete icon SHALL also NOT be displayed on task cards in the Running column, regardless of the user's role.

#### Scenario: Viewer cannot see delete button
- **WHEN** a viewer user views a task card in any column
- **THEN** the delete icon is not rendered on the card

#### Scenario: Editor sees delete button on non-running task
- **WHEN** an editor views a task card in the New column
- **THEN** the delete icon is visible on the card

#### Scenario: No delete button on running tasks
- **WHEN** any user views a task card in the Running column
- **THEN** the delete icon is not rendered on the card

#### Scenario: Delete button visible on completed task for editor
- **WHEN** an editor views a task card in the Completed column
- **THEN** the delete icon is visible on the card
