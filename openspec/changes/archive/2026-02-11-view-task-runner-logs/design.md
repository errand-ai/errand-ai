## Context

The task runner container writes structured JSON results to stdout and diagnostic logs to stderr. The worker captures both streams separately (`container.logs(stdout=True/False, stderr=True/False)`), already truncates each to 1MB (`truncate_output`), but only persists `parsed.result` (the structured result string) in the `output` column on success. On failure/retry, it stores the combined `stderr + "\n" + stdout` in `output`. In neither case are the stderr logs preserved independently — they are either discarded (success) or mixed into output (failure).

The `TaskResponse` Pydantic model and the worker's `_task_to_dict()` helper both serialize the `output` field. The `TaskEditModal` currently has no reference to output or logs.

## Goals / Non-Goals

**Goals:**
- Persist task runner stderr logs in a dedicated column so they survive successful execution
- Expose logs through the existing API response and WebSocket events
- Display logs in the TaskEditModal behind a collapsible section, only visible when logs exist

**Non-Goals:**
- Streaming/live log viewing during task execution
- Log rotation, retention policies, or separate log storage
- Changing the existing `output` field behaviour (it continues to hold `parsed.result` on success)
- Adding logs to the TaskOutputModal (that modal shows `output`, not logs)

## Decisions

### 1. New `runner_logs` column on tasks table

Add a nullable `Text` column `runner_logs` to the `tasks` table. The worker writes stderr into this field on every execution (success, retry, failure). This keeps the existing `output` field semantics unchanged.

**Alternative considered**: Overload the `output` field to always include stderr. Rejected because `output` is already displayed in the TaskOutputModal and used by the needs_input flow — mixing logs into it changes established behaviour.

### 2. Worker stores stderr unconditionally

In the worker's main loop, after `process_task_in_container` returns `(exit_code, stdout, stderr)`, always write `stderr` to `runner_logs` regardless of outcome. This is a single additional column in each `UPDATE` statement. The existing `truncate_output()` call on stderr (1MB limit) provides size safety.

### 3. Add `runner_logs` to API response and WebSocket events

Add `runner_logs: Optional[str] = None` to `TaskResponse` and include it in `from_task()`. Add `"runner_logs": task.runner_logs` to `_task_to_dict()` in the worker. No new endpoints needed — the field rides on existing task serialization.

### 4. Collapsible section in TaskEditModal

Add a `<details>` / `<summary>` HTML element below the action buttons in the TaskEditModal. Conditionally rendered only when `task.runner_logs` is non-null. The log content is displayed in a `<pre>` block with monospace font, `overflow-auto`, and `max-h-64` to keep it bounded. The section is collapsed by default.

**Alternative considered**: A separate modal (like TaskOutputModal). Rejected because the user explicitly wants it in the edit modal, and a `<details>` element is simpler and keeps context together.

### 5. Alembic migration

Single migration adding the `runner_logs` column as nullable Text with no default. Safe to deploy — no data backfill needed, existing rows get `NULL`.

## Risks / Trade-offs

- **Storage growth**: Every task execution now stores up to 1MB of logs (already truncated by `truncate_output`). Acceptable for the current scale; if it becomes an issue, a retention policy can be added later (non-goal for now).
- **Backward compatibility**: The new `runner_logs` field is nullable and optional in the API response. Existing frontend code that doesn't use it is unaffected. No breaking changes.
- **Migration**: Adding a nullable column with no default is a safe, non-locking operation in PostgreSQL.
