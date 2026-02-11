## 1. Database

- [x] 1.1 Add `runner_logs` column to Task model in `backend/models.py` (nullable Text)
- [x] 1.2 Generate Alembic migration for the new `runner_logs` column

## 2. Backend API

- [x] 2.1 Add `runner_logs` field to `TaskResponse` Pydantic model and `from_task()` method in `backend/main.py`
- [x] 2.2 Ensure `runner_logs` is excluded from the PATCH update logic (read-only field, not writable via API)

## 3. Worker

- [x] 3.1 Update worker to store stderr in `runner_logs` on successful execution (both `completed` and `needs_input` paths)
- [x] 3.2 Update `_schedule_retry()` and failure paths to store stderr in `runner_logs`
- [x] 3.3 Add `runner_logs` to `_task_to_dict()` helper for WebSocket events

## 4. Frontend

- [x] 4.1 Add `runner_logs` field to the task type in the frontend store/types
- [x] 4.2 Add collapsible "Task Runner Logs" section to `TaskEditModal.vue` below action buttons, visible only when `runner_logs` is non-null, with monospace `<pre>` block

## 5. Tests

- [x] 5.1 Add backend tests for `runner_logs` in API responses (null for new tasks, present after processing)
- [x] 5.2 Add backend tests for worker storing stderr in `runner_logs` across all execution outcomes
- [x] 5.3 Add frontend tests for the collapsible logs section (hidden when null, visible when present, content displayed)
