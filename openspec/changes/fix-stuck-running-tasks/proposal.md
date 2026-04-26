## Why

Tasks can get permanently stuck in "running" status with no corresponding container, leaving them orphaned on the Kanban board. Two bugs cause this:

1. **CancelledError bypasses retry scheduling**: When the task manager's processing coroutine is cancelled (e.g., during advisory lock loss or shutdown), `asyncio.CancelledError` is a `BaseException` in Python 3.9+ and is not caught by the `except Exception` handler. The task's exit code is logged but `_schedule_retry` never executes, leaving the task in "running" permanently.

2. **Orphaned task recovery crashes on startup**: `_recover_orphaned_task` uses `asyncio.run()` to perform async DB operations, but it's called during FastAPI startup which already has an active event loop. This causes `RuntimeError: got Future attached to a different loop`, the recovery silently fails, and the orphaned task stays in "running".

Both were observed in production on 2026-04-26 during a deployment rollover (ArgoCD sync + migration scale-down). Two tasks were left stuck in "running" with no K8s Jobs backing them.

## What Changes

- Add `except asyncio.CancelledError` handler in the task processing coroutine that calls `_schedule_retry` before re-raising, ensuring cancelled tasks are always moved out of "running"
- Convert `_recover_orphaned_task` from `asyncio.run()` to an async function called from the existing event loop, fixing the "different loop" crash
- Add a safety net in the zombie cleanup to catch tasks that slip through both mechanisms

## Capabilities

### New Capabilities

(none)

### Modified Capabilities
- `task-runner-error-resilience`: Task processing must handle CancelledError and ensure retry scheduling
- `container-runtime`: Orphaned task recovery must work correctly within the existing event loop

## Impact

- **errand/task_manager.py**: Add CancelledError handler in `_run_task` between GitSkillsError and Exception handlers
- **errand/container_runtime.py**: Convert `_recover_orphaned_task` to async, change `cleanup_orphaned_jobs` to accept an event loop or use the running loop
- **No migration needed**: This is a bug fix with no schema changes
- **No frontend changes**: Backend-only fix
