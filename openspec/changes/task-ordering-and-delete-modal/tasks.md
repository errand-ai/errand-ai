## 1. Database: Add position column

- [x] 1.1 Add `position` integer column to the Task model in `backend/models.py` (nullable initially for migration, default 0)
- [x] 1.2 Create Alembic migration `006_add_task_position.py`: add column, backfill positions per status group ordered by `created_at`, set NOT NULL with default 0
- [x] 1.3 Add `position` field to `TaskResponse` in `backend/main.py` and update `from_task` to include it

## 2. Backend: Position assignment on create and status change

- [x] 2.1 Add helper function `_next_position(session, status)` that returns `MAX(position) + 1` for tasks with the given status (or 1 if none exist)
- [x] 2.2 Update `POST /api/tasks` to assign position using `_next_position` based on the task's final status (after auto-routing)
- [x] 2.3 Update `PATCH /api/tasks/{id}` to assign new position at bottom of target column when `status` changes
- [x] 2.4 Update `PATCH /api/tasks/{id}` to handle `position` field for intra-column reordering: shift tasks with position >= new value, set task to new position

## 3. Backend: Query ordering

- [x] 3.1 Change `GET /api/tasks` ordering from `created_at desc` to `position asc, created_at asc`
- [x] 3.2 Update worker `dequeue_task` in `backend/worker.py` to order by `position asc, created_at asc` instead of `created_at`

## 4. Backend: Tests

- [x] 4.1 Add tests for position assignment on task creation (new task gets bottom position)
- [x] 4.2 Add tests for position reassignment on status change (task moves to bottom of new column)
- [x] 4.3 Add tests for intra-column reorder via PATCH with `position` field (shift logic)
- [x] 4.4 Add tests for `GET /api/tasks` returning tasks ordered by position
- [x] 4.5 Update existing tests in `test_tasks.py` that assert on response fields to include `position`

## 5. Frontend: Add position to data model and API

- [x] 5.1 Add `position` field to `TaskData` interface in `frontend/src/composables/useApi.ts`
- [x] 5.2 Add `position` to the `updateTask` function signature in `useApi.ts`
- [x] 5.3 Update `tasksByStatus` in `frontend/src/stores/tasks.ts` to sort: Scheduled by `execute_at` ascending (nulls last), all others by `position` ascending then `created_at` ascending
- [x] 5.4 Update WebSocket `task_created` handler to insert new tasks at the end of the array (not prepended) so position ordering is preserved

## 6. Frontend: Intra-column drag-and-drop reordering

- [x] 6.1 Extend drag-and-drop handlers in `KanbanBoard.vue` to detect intra-column drops (same status) and calculate target position from drop index
- [x] 6.2 On intra-column drop in New or Pending columns, call `PATCH /api/tasks/{id}` with `{"position": N}`
- [x] 6.3 Add visual drop indicator between cards during intra-column drag in New and Pending columns
- [x] 6.4 Disable intra-column reordering for Scheduled, Running, Review, and Completed columns

## 7. Frontend: Delete confirmation modal

- [x] 7.1 Add inline `<dialog>` delete confirmation modal in `KanbanBoard.vue` with Tailwind styling matching TaskEditModal (backdrop overlay, rounded card, red Delete button, Cancel button)
- [x] 7.2 Replace native `confirm()` call in `onDelete` with modal: store task reference, show modal, handle confirm/cancel
- [x] 7.3 Update `onModalDelete` (delete from edit modal) to also use the styled confirmation modal instead of native confirm
- [x] 7.4 Handle backdrop click and Escape key to dismiss the delete modal

## 8. Frontend: Tests

- [x] 8.1 Add tests for `tasksByStatus` sorting: position-based for non-Scheduled, execute_at-based for Scheduled
- [x] 8.2 Add tests for delete confirmation modal: renders on delete click, confirm triggers API call, cancel dismisses
- [x] 8.3 Update existing KanbanBoard and TaskCard tests to include `position` in task fixtures
- [x] 8.4 Add tests for intra-column drag-and-drop reorder (dispatching drop event within same column triggers PATCH with position)
