## Why

When a worker crashes or is restarted mid-task, any task with `status="running"` is stranded — it stays in "running" forever because no recovery mechanism exists. The scheduler only promotes scheduled→pending tasks; it has no awareness of stale running tasks. In K8s mode, the worker's startup cleanup deletes all orphaned Jobs indiscriminately without updating the corresponding task status in the database. The result is zombie tasks that block the user's workflow and require manual intervention to recover.

## What Changes

- Add a periodic zombie task detection loop in the main service (alongside the existing scheduler) that scans for tasks stuck in "running" state beyond a configurable timeout
- Add a `heartbeat_at` timestamp field on the Task model, updated by the worker periodically while a task is executing, so the main service can distinguish live tasks from stale ones
- When a zombie task is detected (stale heartbeat + no active container/job), move it back to "scheduled" for automatic retry, or to "review" if retry count is exhausted
- In K8s mode, cross-reference orphaned Jobs with the task database before deleting, and update task status accordingly
- Publish `task_updated` WebSocket events when zombie tasks are recovered so the frontend reflects the change immediately

## Capabilities

### New Capabilities
- `zombie-task-recovery`: Periodic detection and recovery of tasks stuck in "running" state — heartbeat tracking, stale task detection, status recovery, and orphaned container cleanup

### Modified Capabilities
- `task-worker`: Worker updates `heartbeat_at` on the task row periodically during execution
- `k8s-task-execution`: Startup cleanup cross-references orphaned Jobs with task DB and updates task status

## Impact

- **errand/models.py**: New `heartbeat_at` column on Task model
- **errand/alembic/**: Migration to add `heartbeat_at` column
- **errand/worker.py**: Heartbeat update logic during task execution (periodic DB write in the log-streaming loop)
- **errand/main.py**: New `run_zombie_cleanup()` background task in lifespan, similar to `run_scheduler()`
- **errand/container_runtime.py**: K8s cleanup improved to cross-reference task DB
- **Helm chart**: No changes expected — cleanup runs inside existing server/worker pods
- **Dependencies**: No new dependencies
