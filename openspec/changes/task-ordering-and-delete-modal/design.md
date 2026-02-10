## Context

Tasks currently have no explicit ordering — `GET /api/tasks` returns all tasks sorted by `created_at desc`, and the frontend renders cards in that order within each column. The worker dequeues pending tasks by `created_at asc`. There is no mechanism for users to control card order, and the Scheduled column doesn't sort by upcoming execution time. The delete confirmation uses the browser's native `confirm()` dialog, which is visually inconsistent with the app's Tailwind-styled modals (e.g. TaskEditModal).

## Goals / Non-Goals

**Goals:**
- Explicit position-based ordering within each kanban column
- New tasks appear at the bottom of their target column
- Scheduled column sorted by `execute_at` ascending (soonest at top)
- Users can drag to reorder cards within New and Pending columns
- Styled delete confirmation modal matching existing UI patterns
- Worker dequeues by position order (respecting user-defined priority)

**Non-Goals:**
- Cross-column ordering (existing inter-column drag-and-drop is unchanged)
- Keyboard-based reordering (drag-and-drop only for now)
- Undo/redo for reorder operations
- Batch reordering or sorting controls (e.g. "sort by date" button)

## Decisions

### 1. Position field on the Task model

Add an integer `position` column to the `tasks` table, defaulting to 0. Position is meaningful within a status group — tasks with the same status are ordered by position ascending (lower = higher on screen).

**Rationale**: A simple integer column is the most straightforward approach. We don't need fractional positions or linked-list ordering given the expected task volume (tens to low hundreds per column, not thousands).

**Alternative considered**: Fractional positions (float) to avoid shifting adjacent rows on reorder. Rejected because integer shifting is simpler, there are few tasks per column, and a single UPDATE with a range condition handles it efficiently.

### 2. Position assignment on creation and status change

When a task is created or moved to a new column (status change), it gets position = `MAX(position) + 1` for tasks in that status group. This places it at the bottom of the column.

For the Scheduled column, position is stored but ignored for display — the frontend sorts Scheduled tasks by `execute_at` ascending. Position is still maintained so if a task moves out of Scheduled, it has a valid position.

**Rationale**: Bottom-of-column placement is the least surprising default. The Scheduled column's natural ordering is time-based, which the user specifically requested.

### 3. Reorder via PATCH endpoint

Extend the existing `PATCH /api/tasks/{id}` to accept a `position` field. When position is provided, the backend:
1. Determines the task's current status (column)
2. Removes the task from its current position (shifts tasks above down)
3. Inserts at the new position (shifts tasks at and below up)
4. Updates the task's position

This keeps the API surface minimal — no new endpoint needed.

**Alternative considered**: Dedicated `POST /api/tasks/{id}/reorder` endpoint. Rejected to keep the API consistent; PATCH already handles partial updates.

### 4. Position shifting strategy

When a task is inserted at position N:
- All tasks in the same status with position >= N get position += 1
- The moved task gets position = N

When a task leaves a column (status change), no gap-closing is needed immediately — gaps in position values don't affect ordering. Periodic compaction could be added later if needed.

**Rationale**: Shifting on insert is a single UPDATE statement. Gaps are harmless and avoiding gap-closing reduces write amplification on status changes.

### 5. Worker dequeue order

Change the worker's `dequeue_task` query from `ORDER BY created_at` to `ORDER BY position, created_at`. This means user-reordered priority in the Pending column is respected by the worker.

**Rationale**: If a user drags a task to the top of the Pending column, they expect it to be processed first.

### 6. Delete confirmation modal

Replace the native `confirm()` call with a `<dialog>` element styled with Tailwind CSS, consistent with the existing TaskEditModal pattern. The modal will be a lightweight inline component within KanbanBoard.vue (not a separate component file) since it's simple — just a message, confirm button, and cancel button.

**Alternative considered**: Separate `DeleteConfirmModal.vue` component. Rejected because the delete modal is trivially simple (no form fields, no state) — a `<dialog>` element with a few divs is sufficient inline. If it grows more complex later, it can be extracted.

### 7. API response ordering

`GET /api/tasks` will continue to return a flat array, but ordered by: `position ASC, created_at ASC` within each status group. The frontend groups tasks by status and renders each group in the order received.

**Alternative considered**: Return tasks pre-grouped by status. Rejected because it would be a breaking API change and the frontend already groups by status client-side.

## Risks / Trade-offs

- **Position gaps accumulate over time** → Harmless for ordering; can add a compaction migration later if row counts grow significantly
- **Concurrent reorder requests could conflict** → The PATCH endpoint runs in a transaction; `SELECT FOR UPDATE` on the affected rows prevents lost updates. Acceptable for single-user or low-concurrency use.
- **Backfill migration for existing tasks** → Alembic migration assigns positions based on current `created_at` order per status group. Reversible by dropping the column.

## Migration Plan

1. Alembic migration: add `position` integer column (nullable initially), backfill per status group ordered by `created_at`, then set NOT NULL with default 0
2. Deploy backend with new ordering logic
3. Deploy frontend with intra-column drag-and-drop and delete modal
4. Rollback: revert frontend, revert backend, drop column via down migration
