## MODIFIED Requirements

### Requirement: Worker cleans up orphaned Jobs on startup

When using KubernetesRuntime, the worker SHALL check for orphaned task-runner Jobs (labelled with `app.kubernetes.io/managed-by: content-manager-worker`) on startup and delete them. For each orphaned Job found, the worker SHALL:

1. Read the `content-manager/task-id` label from the Job metadata
2. Query the `tasks` table for the corresponding task
3. If the task exists and has `status = "running"`:
   - Move the task to `status = "scheduled"` with exponential backoff `execute_at` and increment `retry_count` (using the same retry formula as `_schedule_retry`)
   - If `retry_count >= 5`, move to `status = "review"` instead with output indicating the task was recovered during worker startup
   - Publish a `task_updated` WebSocket event
4. Delete the orphaned Job and its associated ConfigMap and Secrets

This replaces the previous behaviour of deleting all orphaned Jobs indiscriminately without updating task status.

#### Scenario: Orphaned Job with running task recovered on startup

- **WHEN** the worker starts and finds an orphaned Job labelled with task ID `abc-123`, and that task has `status="running"` in the database
- **THEN** the worker moves the task to `status="scheduled"` with backoff, deletes the Job/ConfigMap, and publishes a `task_updated` event

#### Scenario: Orphaned Job with non-running task cleaned up silently

- **WHEN** the worker starts and finds an orphaned Job labelled with task ID `abc-123`, and that task has `status="completed"` in the database
- **THEN** the worker deletes the Job/ConfigMap without modifying the task

#### Scenario: Orphaned Job with missing task cleaned up silently

- **WHEN** the worker starts and finds an orphaned Job with a task ID that does not exist in the database
- **THEN** the worker deletes the Job/ConfigMap and logs a warning

#### Scenario: Orphaned Job task with exhausted retries moved to review

- **WHEN** the worker starts and finds an orphaned Job for a task with `status="running"` and `retry_count >= 5`
- **THEN** the worker moves the task to `status="review"` with output indicating startup recovery
