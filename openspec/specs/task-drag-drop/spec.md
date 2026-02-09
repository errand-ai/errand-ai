## Requirements

### Requirement: User can drag task cards between columns
The frontend SHALL allow users to drag a task card from one kanban column and drop it onto another column. The drag interaction SHALL use the HTML5 Drag and Drop API.

#### Scenario: Drag a task from New to Scheduled
- **WHEN** the user drags a task card from the "New" column and drops it on the "Scheduled" column
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}` and the card moves to the Scheduled column

#### Scenario: Drag feedback during drag operation
- **WHEN** the user begins dragging a task card
- **THEN** the dragged card SHALL display a visual drag indicator and valid drop target columns SHALL be visually highlighted

#### Scenario: Drop on the same column
- **WHEN** the user drags a task card and drops it back on the same column
- **THEN** no API call is made and the card remains in its current position

### Requirement: Failed drag-and-drop reverts on next poll
If the `PATCH` request fails after a drop, the frontend SHALL NOT optimistically update the card position. The card SHALL revert to its server-side status on the next poll cycle.

#### Scenario: API failure during drag
- **WHEN** the user drops a task card on a new column and the `PATCH /api/tasks/{id}` request fails
- **THEN** the frontend displays an error message and the card returns to its original column on the next poll refresh
