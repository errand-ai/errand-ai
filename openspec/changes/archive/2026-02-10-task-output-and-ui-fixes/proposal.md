## Why

After the worker moves a task from pending to running, the task description disappears from the edit modal. This is because the worker's WebSocket event payload (`_task_to_dict`) omits several fields including `description` — and the frontend replaces the entire task object on update, losing the data. Additionally, once tasks reach review/completed status, there is no way for users to view the captured execution output, and the edit modal still shows the scheduling time rather than when processing completed.

## What Changes

- **Fix worker WebSocket event payload**: `_task_to_dict()` must include all fields that `TaskResponse` serialises (description, position, category, tags, etc.) so partial updates don't blank out fields in the frontend
- **Show completion time in edit modal**: For tasks in review or completed status, display the `updated_at` timestamp (when processing finished) instead of `execute_at`
- **Add output viewer popup**: New popup accessible from a button on task cards in review, completed, and scheduled columns, displaying the captured execution output (stdout/stderr or error message)

## Capabilities

### New Capabilities
- `task-output-viewer`: Popup component for viewing captured task execution output, triggered from task cards

### Modified Capabilities
- `task-worker`: Fix `_task_to_dict()` to include all task fields in WebSocket event payloads (description, position, category, repeat_interval, repeat_until, tags)
- `task-edit-modal`: Show `updated_at` as completion time instead of `execute_at` for tasks in review or completed status
- `kanban-frontend`: Add output viewer button to task cards in review, completed, and scheduled columns

## Impact

- `backend/worker.py` — update `_task_to_dict()` to serialise all fields
- `frontend/src/components/TaskCard.vue` — add output button conditionally
- `frontend/src/components/TaskEditModal.vue` — conditional time display logic
- New frontend component for the output viewer popup
- Backend and frontend tests for the changes
