## Why

The "New" column on the Kanban board serves as a holding area for tasks that the system couldn't fully process — short inputs (5 words or fewer) and LLM failures. In practice it is rarely used and wastes horizontal space. The "Review" column already serves a similar purpose (tasks needing human attention), so tasks that would have gone to "New" can go to "Review" instead. Removing the column simplifies the board and gives each remaining column more space.

## What Changes

- **BREAKING**: Remove the `new` status from the task workflow. The `new` column is removed from the Kanban board.
- Move the "Review" column to be the first (leftmost) column on the board
- Tasks that currently land in `new` status (short input or LLM failure with "Needs Info" tag) SHALL instead be created with status `review`
- The auto-promotion logic (editing a `new` + "Needs Info" task to add description + scheduling → `scheduled`) is removed since there is no `new` status
- Remove `new` from `VALID_STATUSES` in the backend
- Update drag-and-drop: reorderable columns change from `['new', 'pending']` to `['review', 'pending']`
- Update skeleton loading state to show 5 columns instead of 6
- Existing tasks with status `new` in the database SHALL be migrated to `review` via an Alembic migration

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `kanban-frontend`: Remove the "New" column, move "Review" to first position, update column order and skeleton loading
- `task-categorisation`: Change auto-routing to send "Needs Info" tasks to `review` instead of `new`; remove auto-promotion from `new` on edit
- `task-api`: Remove `new` from `VALID_STATUSES`; add migration to move existing `new` tasks to `review`
- `task-drag-drop`: Update reorderable columns from `['new', 'pending']` to `['review', 'pending']`; remove scenarios referencing "New" column

## Impact

- **backend/main.py**: `VALID_STATUSES` loses `new`; task creation routing changes; auto-promotion logic removed; PATCH endpoint updated
- **backend/alembic/**: New migration to update `status='new'` → `status='review'` for existing tasks
- **frontend/src/components/KanbanBoard.vue**: Column array reordered (Review first), "New" column removed, `REORDERABLE_COLUMNS` updated, skeleton count reduced
- **frontend/src/components/TaskCard.vue**: References to `new` column status removed
- **Tests**: Backend and frontend tests referencing `new` status updated to use `review`
