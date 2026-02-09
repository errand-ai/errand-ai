## Context

The kanban board currently has four hardcoded columns (Pending, Running, Completed, Failed) with no user interaction beyond task creation. Task cards are display-only — no editing, no drag-and-drop. The backend has `GET` (list/single) and `POST` (create) endpoints but no update endpoint. The `status` field is an unconstrained text column in PostgreSQL with a server default of `'pending'`.

The frontend uses a Pinia store (`tasks.ts`) that polls `GET /api/tasks` every 5 seconds, with computed properties filtering by each status. The `TaskStatus` type in `useApi.ts` is a union of the four current statuses.

## Goals / Non-Goals

**Goals:**
- Replace the four columns with seven: New, Need Input, Scheduled, Pending, Running, Review, Completed
- Enable drag-and-drop to move cards between columns, persisting the status change via API
- Provide an edit modal to update task title and status
- Add a `PATCH /api/tasks/{id}` backend endpoint
- Migrate existing data to the new status set

**Non-Goals:**
- Worker process changes — the worker currently transitions pending → running → completed/failed; updating worker logic is out of scope for this change
- Role-based restrictions on which columns a user can drag to
- Task ordering within a column (cards remain sorted by creation time)
- Adding new task fields beyond title and status (e.g. description, assignee, priority)

## Decisions

### D1: Status values and mapping

**Decision**: Use lowercase kebab-case status strings stored as text in PostgreSQL.

New statuses: `new`, `need-input`, `scheduled`, `pending`, `running`, `review`, `completed`

Migration mapping for existing data:
- `pending` → `pending` (no change)
- `running` → `running` (no change)
- `completed` → `completed` (no change)
- `failed` → `new` (failed tasks resurface for triage)

**Rationale**: Keeping status as a text column avoids a PostgreSQL enum migration (which requires `ALTER TYPE` and is awkward with Alembic). Status validation happens in the API layer. Kebab-case is consistent and URL-friendly. Mapping `failed` → `new` is the safest default — these tasks need human attention.

### D2: Drag-and-drop approach

**Decision**: Use the HTML5 Drag and Drop API directly (no library).

**Alternatives considered**:
- **vuedraggable / sortablejs**: Full-featured but adds a dependency for a simple column-to-column move. We don't need within-column reordering.
- **@vueuse/integrations drag**: Lightweight but still a dependency.

**Rationale**: We only need to drag a card from one column and drop it on another — no sorting within columns, no nested drag targets. The native HTML5 API handles this with `draggable`, `dragstart`, `dragover`, `drop` events and a few lines of code. This keeps the bundle small and avoids dependency management.

### D3: PATCH endpoint design

**Decision**: Add `PATCH /api/tasks/{id}` accepting a partial JSON body with optional `title` and `status` fields. Validate `status` against the allowed set server-side. Return the updated task.

```
PATCH /api/tasks/{id}
Body: { "title"?: string, "status"?: string }
Response: 200 with updated TaskResponse
Errors: 404 (not found), 422 (invalid status or empty title)
```

**Rationale**: PATCH with optional fields is idiomatic for partial updates. A single endpoint serves both drag-and-drop (status-only update) and the edit modal (title + status update). Validation on the backend ensures only valid statuses are accepted regardless of client behavior.

### D4: Edit modal component

**Decision**: Create a new `TaskEditModal.vue` component using a `<dialog>` element with Vue's `v-model` pattern. The modal receives the task as a prop, emits `save` and `cancel` events. The parent component handles the API call.

**Rationale**: The native `<dialog>` element provides built-in modal behavior (focus trapping, backdrop, Escape to close) without a UI library. Keeping API logic in the parent (KanbanBoard) maintains the existing pattern where the store handles all data operations.

### D5: Frontend status type and store refactor

**Decision**: Replace the hardcoded `TaskStatus` union and per-status computed properties with a data-driven approach:
- Define a `COLUMNS` array (ordered) as the source of truth for column key, label, and color
- Replace four computed getters with a single `tasksByStatus(status)` method or a computed map
- The `TaskStatus` type becomes a union of the new seven statuses

**Rationale**: The current approach (one computed per status) doesn't scale to seven columns. A data-driven column definition makes it trivial to adjust columns in the future and eliminates the switch statement in `KanbanBoard.vue`.

### D6: Grid layout

**Decision**: Change from `grid-cols-4` to `grid-cols-7` in the kanban board. On smaller screens, allow horizontal scrolling rather than stacking columns.

**Rationale**: Seven columns won't fit in a stacked mobile layout. Horizontal scroll is the standard pattern for kanban boards (Trello, Jira, etc.) and keeps cards readable.

## Risks / Trade-offs

- **Worker incompatibility**: The worker still uses `pending` → `running` → `completed`/`failed` transitions. After this change, tasks in `new`, `need-input`, `scheduled`, or `review` won't be picked up by the worker. → *Mitigation*: This is acceptable — the worker should only process `pending` tasks, which is already its behavior. A follow-up change should update the worker to handle the full lifecycle.

- **No status transition validation**: Any status can be changed to any other status via drag or edit. There are no workflow rules (e.g. "can only move from New to Scheduled"). → *Mitigation*: Intentional for now — keep it flexible. Workflow rules can be added later if needed.

- **Optimistic UI not implemented**: Drag-and-drop will call the API and then reload. If the API fails, the card snaps back on the next poll cycle (up to 5 seconds). → *Mitigation*: Acceptable for MVP. The 5-second poll interval means the UI self-corrects quickly. Optimistic updates can be added later.

- **Migration on existing data**: The Alembic migration updates status values in-place. → *Mitigation*: The migration is a simple `UPDATE` statement, fully reversible with a down migration that maps back.
