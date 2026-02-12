## Why

When the worker encounters an error processing a task (non-zero exit code, unparseable output, Docker error), it moves the task back to the Scheduled column with exponential backoff. However, there is no visual indicator in the UI explaining why the task reappeared in Scheduled. Users see a task they thought was being processed sitting in Scheduled with no context.

## What Changes

- The worker's `_schedule_retry` function will add a "Retry" tag to the task when moving it back to Scheduled, following the same pattern used for "Input Needed" tags on needs_input tasks
- The "Retry" tag will be removed when the task is successfully completed or moved to review, so it doesn't persist after a successful run

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-worker`: The retry flow will add a "Retry" tag to the task, and the success/review flow will remove it if present

## Impact

- `backend/worker.py`: `_schedule_retry` adds "Retry" tag; success path in `run()` removes it
- No frontend changes needed — tags already render in the kanban UI
- No database migration — uses existing `tags` and `task_tags` tables
