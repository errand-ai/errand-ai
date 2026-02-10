## 1. Fix worker WebSocket event payload

- [x] 1.1 Update `_task_to_dict()` in `backend/worker.py` to include all fields: description, position, category, execute_at, repeat_interval, repeat_until, tags (as sorted list of tag names), created_at, updated_at — matching `TaskResponse.from_task()`
- [x] 1.2 Ensure task tags relationship is loaded before calling `_task_to_dict()` (use `selectinload` or access after refresh)
- [x] 1.3 Add/update backend test to verify `_task_to_dict()` returns all expected fields including description and tags

## 2. WebSocket event payload schema regression tests

- [x] 2.1 Add backend test that asserts `_task_to_dict()` output keys exactly match `TaskResponse` schema fields (id, title, description, status, position, category, execute_at, repeat_interval, repeat_until, output, retry_count, tags, created_at, updated_at) — test fails if any field is added to `TaskResponse` but missing from `_task_to_dict()` or vice versa
- [x] 2.2 Add backend test that patches a task via API and captures the WebSocket `task_updated` event, asserting the event payload contains all `TaskResponse` fields with correct types (strings, lists, nullables)
- [x] 2.3 Add backend test that simulates worker status transitions (pending→running, running→review) via `_task_to_dict()` and asserts description, tags, and position are preserved in every emitted payload

## 3. Task edit modal — completion time

- [x] 3.1 In `TaskEditModal.vue`, for tasks with status `review` or `completed`, display `updated_at` as "Completed at" formatted datetime (read-only) instead of the `execute_at` datetime picker
- [x] 3.2 Add frontend test for TaskEditModal: verify "Completed at" is shown for review status tasks
- [x] 3.3 Add frontend test for TaskEditModal: verify execute_at picker is shown for non-review/completed tasks

## 4. Task output viewer popup

- [x] 4.1 Create `TaskOutputModal.vue` component: `<dialog>` element with task title header, scrollable monospace `<pre>` block for output, Close button, backdrop click and Escape to dismiss
- [x] 4.2 Handle empty/null output with "No output available" message
- [x] 4.3 Add frontend tests for TaskOutputModal: rendering output, empty state, close behaviour

## 5. Task card output button

- [x] 5.1 In `TaskCard.vue`, add "View Output" button (eye icon) shown when `columnStatus` is `review`, `completed`, or `scheduled` AND task has non-null `output`
- [x] 5.2 Wire the button to open `TaskOutputModal` with the selected task
- [x] 5.3 Add frontend test for TaskCard: output button visibility in review/completed/scheduled columns
- [x] 5.4 Add frontend test for TaskCard: output button hidden when output is null

## 6. Version bump and integration

- [x] 6.1 Bump VERSION file
- [x] 6.2 Run full backend and frontend test suites, fix any failures
