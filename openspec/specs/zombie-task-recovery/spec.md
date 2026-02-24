## Requirements

### Requirement: Zombie task detection and recovery loop

The main service SHALL run a periodic background task (`run_zombie_cleanup`) alongside the existing scheduler that detects and recovers zombie tasks. The loop SHALL:

1. Acquire a distributed lock via Valkey (`errand:zombie-cleanup-lock`, TTL 30s) to prevent concurrent execution across replicas
2. Query all tasks with `status = "running"` and `heartbeat_at < NOW() - ZOMBIE_TIMEOUT` (configurable via `ZOMBIE_TIMEOUT_SECONDS` env var, default 300 seconds / 5 minutes)
3. For each stale task, move it back to `scheduled` with `execute_at` set using the existing exponential backoff formula (same as `_schedule_retry`) and increment `retry_count`
4. If the task's `retry_count` has reached the maximum (5), move it to `review` instead of `scheduled`, with `output` set to a message indicating the task was recovered from a zombie state
5. Publish a `task_updated` WebSocket event for each recovered task
6. Log each recovery at INFO level with the task ID and how long it was stale

The loop SHALL run at a configurable interval (`ZOMBIE_CLEANUP_INTERVAL` env var, default 60 seconds). The loop SHALL handle errors gracefully — a failed cycle SHALL log a warning and continue to the next cycle.

#### Scenario: Stale running task recovered to scheduled

- **WHEN** a task has `status="running"` and `heartbeat_at` is older than the zombie timeout
- **THEN** the task is moved to `status="scheduled"` with an exponential backoff `execute_at` and `retry_count` incremented by 1

#### Scenario: Stale running task with exhausted retries moved to review

- **WHEN** a task has `status="running"`, stale heartbeat, and `retry_count >= 5`
- **THEN** the task is moved to `status="review"` with output indicating zombie recovery

#### Scenario: Fresh running task not recovered

- **WHEN** a task has `status="running"` and `heartbeat_at` is within the zombie timeout
- **THEN** the task is left unchanged

#### Scenario: Running task with no heartbeat treated as zombie

- **WHEN** a task has `status="running"` and `heartbeat_at` is NULL (set before heartbeat feature existed)
- **THEN** the task is treated as a zombie and recovered after the timeout period from `updated_at` instead

#### Scenario: WebSocket event published on recovery

- **WHEN** a zombie task is recovered
- **THEN** a `task_updated` event is published containing the updated task data

#### Scenario: Distributed lock prevents concurrent cleanup

- **WHEN** multiple main service replicas are running
- **THEN** only one replica executes the zombie cleanup per cycle

### Requirement: Heartbeat timestamp on Task model

The Task model SHALL include a `heartbeat_at` column (nullable `DateTime` with timezone, default NULL). This column records the last time the worker confirmed it was actively processing the task. The column SHALL be added via an Alembic migration.

The `heartbeat_at` field SHALL be included in the `TaskResponse` API schema and WebSocket event payloads.

#### Scenario: New tasks have NULL heartbeat

- **WHEN** a new task is created
- **THEN** `heartbeat_at` is NULL

#### Scenario: Heartbeat column exists in database

- **WHEN** the Alembic migration runs
- **THEN** the `heartbeat_at` column is added to the `tasks` table as a nullable timestamp with timezone
