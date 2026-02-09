## Why

The current kanban board has four columns (Pending, Running, Completed, Failed) that don't reflect the actual task lifecycle we need. Tasks go through more stages — they may need input, be scheduled for later, or require review before completion. The board also lacks interactivity: users can't drag cards between columns or edit task details without going through the API directly.

## What Changes

- **BREAKING**: Replace the four status columns (pending, running, completed, failed) with seven: **New**, **Need Input**, **Scheduled**, **Pending**, **Running**, **Review**, **Completed**
- **BREAKING**: Remove the `failed` status — failure states will be handled differently in future work
- Add drag-and-drop support so users can move task cards between columns, updating the task status via the API
- Add an edit button to each task card that opens a modal dialog with task fields, Save, and Cancel buttons
- Add a `PATCH /api/tasks/{id}` endpoint to support updating task title and status
- Add a database migration to update existing task statuses to the new set

## Capabilities

### New Capabilities
- `task-drag-drop`: Drag-and-drop interaction for moving task cards between kanban columns, updating task status via the API
- `task-edit-modal`: Modal dialog for editing task details (title, status) with Save and Cancel actions

### Modified Capabilities
- `kanban-frontend`: Column definitions change from (Pending, Running, Completed, Failed) to (New, Need Input, Scheduled, Pending, Running, Review, Completed). Grid layout changes from 4 columns to 7. Task cards gain an edit button and drag handle.
- `task-api`: Add `PATCH /api/tasks/{id}` endpoint for updating task title and status. Valid statuses change to the new set. New tasks default to status `new` instead of `pending`.

## Impact

- **Backend**: `main.py` needs a new PATCH endpoint. Task status validation against the new status set. Default status changes from `pending` to `new`.
- **Database**: Alembic migration to convert existing `pending` → `new`, `failed` → `new`, and add any missing status values. The `status` column remains a text field (no enum constraint).
- **Frontend**: `KanbanBoard.vue` column definitions and grid layout. `TaskCard.vue` gains edit button and drag attributes. New `TaskEditModal.vue` component. A drag-and-drop library (e.g. vuedraggable or native HTML5 drag API) is needed.
- **Specs**: `kanban-frontend/spec.md` and `task-api/spec.md` need delta specs for the new requirements.
- **Worker**: The worker currently transitions tasks from `pending` to `running` to `completed`/`failed`. It will need to be updated to use the new status values in future work, but the immediate scope here is the board UI and API.
