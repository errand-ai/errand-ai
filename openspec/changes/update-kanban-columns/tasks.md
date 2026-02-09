## 1. Backend — Status constants and PATCH endpoint

- [ ] 1.1 Define the valid status list (`new`, `need-input`, `scheduled`, `pending`, `running`, `review`, `completed`) as a constant in `backend/main.py` and add a `TaskUpdate` Pydantic schema with optional `title` (min_length=1) and `status` (validated against the list) fields
- [ ] 1.2 Add `PATCH /api/tasks/{id}` endpoint that accepts `TaskUpdate`, updates only provided fields, and returns the updated `TaskResponse` (404 if not found, 422 if invalid)
- [ ] 1.3 Update `POST /api/tasks` so new tasks default to status `new` instead of `pending` (update model server_default and endpoint logic)

## 2. Database migration

- [ ] 2.1 Create an Alembic migration that updates existing task statuses: `failed` → `new`, and changes the column server_default from `'pending'` to `'new'`
- [ ] 2.2 Add a down migration that reverses the default and maps `new` back to `pending` (for rollback safety)

## 3. Frontend — Update status types and store

- [ ] 3.1 Update `TaskStatus` type in `frontend/src/composables/useApi.ts` to the seven new statuses and add an `updateTask(id, data)` function that calls `PATCH /api/tasks/{id}`
- [ ] 3.2 Refactor `frontend/src/stores/tasks.ts` — replace the four per-status computed properties with a single `tasksByStatus(status)` method or computed map, add an `updateTask` action that calls the API and reloads

## 4. Frontend — Kanban board columns

- [ ] 4.1 Update the `columns` array in `KanbanBoard.vue` to the seven new columns (New, Need Input, Scheduled, Pending, Running, Review, Completed) with appropriate colors, and update the grid from `grid-cols-4` to a 7-column layout with horizontal scroll on small viewports
- [ ] 4.2 Replace the `tasksForColumn` switch statement with a call to the store's `tasksByStatus` method

## 5. Frontend — Drag and drop

- [ ] 5.1 Add `draggable="true"` and `dragstart` handler to `TaskCard.vue` that sets the task ID in the drag data transfer
- [ ] 5.2 Add `dragover` and `drop` handlers to the column containers in `KanbanBoard.vue` that read the task ID, determine the target status, and call the store's `updateTask` action (skip if same column)
- [ ] 5.3 Add visual feedback — highlight the drop target column on `dragenter`/`dragleave` and style the dragged card

## 6. Frontend — Task edit modal

- [ ] 6.1 Create `TaskEditModal.vue` component using a `<dialog>` element with title input, status `<select>` (all seven statuses), Save and Cancel buttons, and client-side validation (title not empty)
- [ ] 6.2 Add an edit button (pencil icon) to `TaskCard.vue` that emits an event with the task data
- [ ] 6.3 Wire up the modal in `KanbanBoard.vue` — open on edit click, call the store's `updateTask` on save, close and discard on cancel/Escape

## 7. Local testing

- [ ] 7.1 Run `docker compose up --build` and verify: migration runs, new tasks get status `new`, all seven columns render, drag-and-drop updates status, edit modal saves changes
