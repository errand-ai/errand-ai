## Purpose

HTML5 drag-and-drop for moving task cards between kanban columns and reordering within columns.

## Requirements

### Requirement: User can drag task cards between columns
The frontend SHALL allow users to drag a task card from one kanban column and drop it onto another column. The drag interaction SHALL use the HTML5 Drag and Drop API. When a task is dropped on a different column, the frontend SHALL send `PATCH /api/tasks/{id}` with the new status. The task SHALL appear at the bottom of the target column.

#### Scenario: Drag a task from Review to Scheduled
- **WHEN** the user drags a task card from the "Review" column and drops it on the "Scheduled" column
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}` and the card moves to the bottom of the Scheduled column

#### Scenario: Drag feedback during drag operation
- **WHEN** the user begins dragging a task card
- **THEN** the dragged card SHALL display a visual drag indicator and valid drop target columns SHALL be visually highlighted

#### Scenario: Drop on the same column
- **WHEN** the user drags a task card and drops it back on the same column without changing position
- **THEN** no API call is made and the card remains in its current position


### Requirement: User can reorder task cards within a column
The frontend SHALL allow users to drag a task card within the Review or Pending column to change its position relative to other cards. When a card is dropped at a new position within the same column, the frontend SHALL send `PATCH /api/tasks/{id}` with the new `position` value. Reordering SHALL NOT be available in the Scheduled, Running, or Completed columns.

#### Scenario: Drag task up in Review column
- **WHEN** the user drags a task card from position 3 to position 1 within the Review column
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with `{"position": 1}` and the card moves to the top of the column

#### Scenario: Drag task down in Pending column
- **WHEN** the user drags a task card from position 1 to position 3 within the Pending column
- **THEN** the frontend sends `PATCH /api/tasks/{id}` with `{"position": 3}` and the card moves to the new position

#### Scenario: Reorder not available in Scheduled column
- **WHEN** the user drags a task card within the Scheduled column
- **THEN** no reordering occurs; the column remains sorted by execute_at

#### Scenario: Reorder not available in Running column
- **WHEN** the user attempts to reorder cards in the Running column
- **THEN** no reordering occurs; cards remain in their current position order

#### Scenario: Drop indicator during intra-column drag
- **WHEN** the user drags a task card over other cards in the same column (Review or Pending)
- **THEN** a visual drop indicator SHALL appear between cards showing where the task will be inserted

### Requirement: Failed reorder reverts on next refresh
If the `PATCH` request fails after an intra-column reorder, the frontend SHALL revert the card to its server-side position on the next data refresh.

#### Scenario: API failure during reorder
- **WHEN** the user drops a task card at a new position within a column and the `PATCH /api/tasks/{id}` request fails
- **THEN** the frontend displays an error message and the card returns to its original position on the next refresh

Drag-and-drop SHALL be disabled for users with the `viewer` role. Task cards SHALL NOT have `draggable="true"` when the user is a viewer. Drop target highlighting SHALL not activate for viewer users.

#### Scenario: Viewer cannot drag tasks
- **WHEN** a viewer attempts to drag a task card
- **THEN** the drag operation does not start (card is not draggable)

#### Scenario: Editor can drag tasks
- **WHEN** an editor drags a task card from "Review" to "Scheduled"
- **THEN** the drag-and-drop operates normally

#### Scenario: Admin can drag tasks
- **WHEN** an admin drags a task card between columns
- **THEN** the drag-and-drop operates normally
