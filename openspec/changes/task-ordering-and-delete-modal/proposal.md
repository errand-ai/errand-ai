## Why

Tasks currently appear in reverse-creation order across all columns with no way to control their position. Users cannot prioritise work by reordering cards within a column, new tasks don't consistently land at the bottom, and the Scheduled column doesn't sort by upcoming execution time. Additionally, the delete confirmation uses the browser's native `confirm()` dialog, which looks inconsistent with the app's Tailwind-styled UI.

## What Changes

- Add a `position` (integer) column to the Task model so each task has an explicit sort order within its column
- Backend assigns position automatically: new tasks get the highest position in their column (bottom); tasks moved to Pending by the worker also go to the bottom
- Scheduled column is sorted by `execute_at` ascending (next-to-execute at top), ignoring manual position
- New `PATCH /api/tasks/{id}/reorder` endpoint (or extend existing PATCH) to accept a `position` field for manual reordering
- Frontend enables intra-column drag-and-drop reordering in the New and Pending columns using the existing HTML5 DnD setup
- `GET /api/tasks` returns tasks ordered by position within each status group (except Scheduled, which uses `execute_at`)
- Replace the native `confirm()` delete dialog with a Tailwind-styled `<dialog>` modal consistent with the existing TaskEditModal styling

## Capabilities

### New Capabilities
- `task-ordering`: Explicit position-based ordering of tasks within kanban columns, including automatic placement for new/moved tasks and manual drag-and-drop reordering
- `delete-confirmation-modal`: Styled delete confirmation dialog replacing the native browser confirm popup

### Modified Capabilities
- `task-api`: Add `position` field to task responses; support reordering; change sort order from `created_at desc` to position-based ordering per column
- `kanban-frontend`: Intra-column drag-and-drop reordering in New and Pending columns; Scheduled column sorted by `execute_at`; styled delete confirmation modal replaces native confirm
- `task-drag-drop`: Extend drag-and-drop to support reordering within a column (not just moving between columns)
- `task-worker`: When worker moves a task to Pending, assign it the next position at the bottom of the Pending column

## Impact

- **Database**: New `position` integer column on `tasks` table (Alembic migration required); backfill existing tasks with positions based on current `created_at` order
- **Backend API**: `GET /api/tasks` ordering logic changes; `PATCH /api/tasks/{id}` accepts `position`; new reorder logic to shift positions when a task is inserted
- **Frontend**: KanbanBoard.vue drag-and-drop handlers extended for intra-column reordering; new DeleteConfirmModal component (or inline `<dialog>`); remove native `confirm()` call
- **WebSocket events**: `task_updated` events already cover position changes — no new event types needed
- **Worker**: Minor change to set position when transitioning tasks to Pending
