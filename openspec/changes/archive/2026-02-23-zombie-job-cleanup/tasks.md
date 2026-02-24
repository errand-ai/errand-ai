## 1. Database Model & Migration

- [x] 1.1 Add `heartbeat_at` column (nullable DateTime with timezone, default NULL) to the Task model in `errand/models.py`
- [x] 1.2 Create Alembic migration to add the `heartbeat_at` column to the `tasks` table
- [x] 1.3 Add `heartbeat_at` to the `TaskResponse` schema and `_task_to_dict()` helper in `scheduler.py`

## 2. Worker Heartbeat

- [x] 2.1 Set `heartbeat_at = NOW()` when the worker sets a task to `status = "running"` in `run_worker()`
- [x] 2.2 Create a sync SQLAlchemy engine (lazily initialized from `DATABASE_URL`) for heartbeat updates from the executor thread
- [x] 2.3 Add periodic heartbeat update (every 60 seconds) in the log-streaming loop inside `process_task_in_container()`, wrapped in try/except so failures don't block execution
- [x] 2.4 Write tests for heartbeat: set on running, periodic update during streaming, graceful failure handling

## 3. Zombie Task Recovery Loop

- [x] 3.1 Add `run_zombie_cleanup()` async background loop in `errand/main.py` (or new module), following the `run_scheduler()` pattern with its own Valkey lock (`errand:zombie-cleanup-lock`)
- [x] 3.2 Implement stale task query: `status = "running"` AND (`heartbeat_at < NOW() - timeout` OR (`heartbeat_at IS NULL` AND `updated_at < NOW() - timeout`))
- [x] 3.3 Implement recovery logic: move stale tasks to `scheduled` with exponential backoff (reuse `_schedule_retry` formula) or to `review` if `retry_count >= 5`
- [x] 3.4 Publish `task_updated` WebSocket events for each recovered task
- [x] 3.5 Add `ZOMBIE_TIMEOUT_SECONDS` (default 300) and `ZOMBIE_CLEANUP_INTERVAL` (default 60) env var configuration
- [x] 3.6 Register `run_zombie_cleanup()` in the main service lifespan alongside `run_scheduler()`
- [x] 3.7 Write tests for zombie recovery: stale task recovered, fresh task left alone, NULL heartbeat fallback, max retries → review, distributed lock, WebSocket event published

## 4. K8s Orphaned Job Cleanup Improvement

- [x] 4.1 Modify `cleanup_orphaned_jobs()` in `container_runtime.py` to read `content-manager/task-id` label from each orphaned Job
- [x] 4.2 Query the task database for each orphaned Job's task ID and update task status (running → scheduled with backoff, or → review if retries exhausted) before deleting
- [x] 4.3 Handle edge cases: task not found in DB (log warning, delete Job), task not in running state (delete Job without status change)
- [x] 4.4 Write tests for K8s cleanup: orphaned Job with running task, non-running task, missing task, exhausted retries

## 5. Integration & Verification

- [x] 5.1 Run full test suite (`pytest errand/tests/ -v`) and verify all existing + new tests pass
- [x] 5.2 Test with `docker compose up --build` to verify heartbeat updates work in local dev
- [x] 5.3 Bump VERSION and create PR
