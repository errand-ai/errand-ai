## 1. Database Migration

- [x] 1.1 Create Alembic migration adding `category` (text, nullable, default `'immediate'`), `execute_at` (timestamptz, nullable), `repeat_interval` (text, nullable), and `repeat_until` (timestamptz, nullable) columns to the `tasks` table
- [x] 1.2 Update `Task` model in `backend/models.py` with `category`, `execute_at`, `repeat_interval`, and `repeat_until` mapped columns

## 2. LLM Categorisation

- [x] 2.1 Update `generate_title` in `backend/llm.py` to request structured JSON response with `title`, `category`, `execute_at`, `repeat_interval`, and `repeat_until` fields
- [x] 2.2 Parse the LLM JSON response; fall back to plain title with `immediate` category if JSON parsing fails
- [x] 2.3 Update the function signature/return type to return categorisation data alongside the title
- [x] 2.4 Add "Needs Info" tag on JSON parse failure (consistent with existing LLM failure behaviour)

## 3. Task API — Categorisation Fields

- [x] 3.1 Update `TaskResponse` schema in `backend/main.py` to include `category`, `execute_at`, `repeat_interval`, and `repeat_until` fields
- [x] 3.2 Update `POST /api/tasks` to pass LLM categorisation data (category, execute_at, repeat_interval, repeat_until) when creating the task
- [x] 3.3 Implement auto-routing logic in `POST /api/tasks`: if no "Needs Info" tag, set status to `pending` for immediate or `scheduled` for scheduled/repeating
- [x] 3.4 Update `PATCH /api/tasks/{id}` to accept optional `category`, `execute_at`, `repeat_interval`, and `repeat_until` fields
- [x] 3.5 Add validation for `category` field in PATCH (must be one of: immediate, scheduled, repeating)
- [x] 3.6 Implement auto-promotion logic in `PATCH /api/tasks/{id}`: if task is in `new` with "Needs Info" tag, and update includes description + scheduling fields (execute_at or repeat_interval), remove "Needs Info" tag and set status to `scheduled`

## 4. Task API — Delete Endpoint

- [x] 4.1 Add `DELETE /api/tasks/{id}` endpoint that deletes the task and its tag associations, returns HTTP 204
- [x] 4.2 Publish `task_deleted` event to Valkey after successful deletion
- [x] 4.3 Return HTTP 404 if the task does not exist

## 5. Frontend Task Type

- [x] 5.1 Update the `Task` TypeScript interface in `frontend/src/stores/tasks.ts` to include `category`, `execute_at`, `repeat_interval`, and `repeat_until` fields
- [x] 5.2 Add a `deleteTask` action to the tasks store that calls `DELETE /api/tasks/{id}` and removes the task from local state
- [x] 5.3 Handle `task_deleted` WebSocket event to remove the task from local state

## 6. Kanban Board Display

- [x] 6.1 Update `TaskCard.vue` to accept and display `execute_at` as a relative time string when the card is in the Scheduled column
- [x] 6.2 Add a helper function or composable for formatting `execute_at` as relative time (e.g. "in 15 minutes", "at 5:00 PM today")
- [x] 6.3 Add a delete icon (trash) to `TaskCard.vue` that shows a confirmation dialog and calls deleteTask on confirm

## 7. Task Edit Modal — Categorisation Fields

- [x] 7.1 Add a category dropdown to `TaskEditModal.vue` with options: Immediate, Scheduled, Repeating
- [x] 7.2 Add an execute_at field using `<input type="datetime-local">` with UTC/local time conversion
- [x] 7.3 Add a repeat_interval text input visible only when category is "repeating", with helper text showing accepted formats (simple intervals and crontab)
- [x] 7.4 Add quick-select buttons (15m, 1h, 1d, 1w) for repeat_interval that populate the input
- [x] 7.5 Add a repeat_until field using `<input type="datetime-local">` visible only when category is "repeating"
- [x] 7.6 Include `category`, `execute_at`, `repeat_interval`, and `repeat_until` in the PATCH request sent on Save

## 8. Task Edit Modal — Delete

- [x] 8.1 Add a "Delete" button to `TaskEditModal.vue` styled as a danger action
- [x] 8.2 Show a confirmation dialog when the Delete button is clicked
- [x] 8.3 On confirmation, call `DELETE /api/tasks/{id}`, close the modal, and remove the task from the board

## 9. Backend Tests

- [x] 9.1 Add tests for LLM categorisation JSON response parsing (success with all fields including repeat_until, invalid JSON fallback, LLM failure fallback)
- [x] 9.2 Add tests for auto-routing logic (immediate→pending, scheduled→scheduled, Needs Info stays new)
- [x] 9.3 Add tests for auto-promotion logic (new+NeedsInfo+description+execute_at → scheduled, description-only stays new, scheduling-only stays new, non-new task unaffected)
- [x] 9.4 Add tests for PATCH with category, execute_at, repeat_interval, and repeat_until fields
- [x] 9.5 Add test for invalid category validation in PATCH
- [x] 9.6 Add tests for DELETE /api/tasks/{id} (success 204, not found 404, event published)

## 10. Frontend Tests

- [x] 10.1 Add tests for TaskCard execute_at display in Scheduled column (shown) vs other columns (hidden)
- [x] 10.2 Add tests for TaskCard delete icon click and confirmation flow
- [x] 10.3 Add tests for TaskEditModal category dropdown, datetime picker, repeat_interval conditional visibility with quick-select buttons, and repeat_until conditional visibility
- [x] 10.4 Add tests for TaskEditModal delete button and confirmation flow
- [x] 10.5 Update existing TaskForm/KanbanBoard tests if affected by new task fields
