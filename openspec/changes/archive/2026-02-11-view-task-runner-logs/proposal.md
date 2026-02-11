## Why

The task runner captures structured results on stdout and logs on stderr, but the worker only persists `parsed.result` in the `output` field on success — stderr logs are discarded. There is no way to view what happened during task execution (agent reasoning, MCP tool calls, warnings), making it difficult to debug or understand task runner behaviour.

## What Changes

- Add a `runner_logs` column to the `tasks` table to persist stderr output from the task runner container, separate from the structured result in `output`
- Modify the worker to store stderr in the new `runner_logs` field for all execution outcomes (success, retry, failure)
- Include `runner_logs` in the task API response and WebSocket events
- Add an expandable "Task Runner Logs" section to the TaskEditModal, visible only when the task has been processed (i.e. `runner_logs` is non-null), displaying the logs in a read-only monospace text panel

## Capabilities

### New Capabilities

### Modified Capabilities
- `task-edit-modal`: Add an expandable logs section below the action buttons, visible only after task processing, with a collapsible monospace text panel showing captured runner logs
- `task-worker`: Store stderr separately in a new `runner_logs` field on every execution, alongside the existing `output` field behaviour
- `task-api`: Include `runner_logs` in the task response schema and PATCH operations
- `database-migrations`: Add `runner_logs` Text column to the tasks table

## Impact

- **Database**: New nullable `runner_logs` column on `tasks` table (requires Alembic migration)
- **Backend**: `worker.py` updated to write stderr to `runner_logs`; `main.py` updated to include `runner_logs` in API responses and WebSocket events; `models.py` updated with new column
- **Frontend**: `TaskEditModal.vue` gains a collapsible log viewer section
- **Tests**: Backend and frontend tests updated for the new field and UI behaviour
