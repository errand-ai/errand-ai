## MODIFIED Requirements

### Requirement: User can drag task cards between columns

_(Append to existing requirement — viewer restriction)_

Drag-and-drop SHALL be disabled for users with the `viewer` role. Task cards SHALL NOT have `draggable="true"` when the user is a viewer. Drop target highlighting SHALL not activate for viewer users.

#### Scenario: Viewer cannot drag tasks
- **WHEN** a viewer attempts to drag a task card
- **THEN** the drag operation does not start (card is not draggable)

#### Scenario: Editor can drag tasks
- **WHEN** an editor drags a task card from "New" to "Scheduled"
- **THEN** the drag-and-drop operates normally

#### Scenario: Admin can drag tasks
- **WHEN** an admin drags a task card between columns
- **THEN** the drag-and-drop operates normally
