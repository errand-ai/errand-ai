## Why

Repeating tasks complete once and stop. When the worker moves a repeating task to the `completed` column, nothing creates the next iteration. Users expect tasks like "check server logs every 30 minutes" to automatically reschedule after each run.

## What Changes

- After the worker completes a repeating task, it checks whether rescheduling is needed:
  - If `repeat_until` is set and has passed, do nothing (series is finished)
  - Otherwise, clone the task with `status = 'scheduled'` and `execute_at` offset by `repeat_interval` from the current time
- The cloned task copies forward: title, description, category, repeat_interval, repeat_until, and tags
- The cloned task does NOT copy: output, runner_logs, retry_count (these start fresh)
- The original completed task stays in the completed column as a historical record
- A `task_created` WebSocket event is published for the new task so the frontend updates in real time

## Capabilities

### New Capabilities
- `repeating-task-rescheduling`: Worker logic to clone and reschedule completed repeating tasks

### Modified Capabilities
- `task-worker`: The worker's task completion flow gains a rescheduling step for repeating tasks

## Impact

- **Backend**: `backend/worker.py` — new rescheduling logic after the `target_status = "completed"` branch, plus a helper to parse `repeat_interval` into a `timedelta`
- **Database**: No schema changes — uses existing Task fields (category, repeat_interval, repeat_until, execute_at)
- **Frontend**: No changes — the existing WebSocket handler and Kanban board already handle new tasks appearing
- **Tests**: New worker tests for rescheduling scenarios (happy path, repeat_until expired, interval parsing)
