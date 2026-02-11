## 1. Scheduler Core

- [x] 1.1 Create `backend/scheduler.py` with `promote_due_tasks()` function that queries tasks where `status = 'scheduled'` and `execute_at <= now()` using `SELECT ... FOR UPDATE SKIP LOCKED`, updates them to `pending`, and publishes `task_updated` WebSocket events for each promoted task
- [x] 1.2 Add Valkey distributed lock functions to `scheduler.py`: `acquire_lock()` using `SET content-manager:scheduler-lock <hostname> NX EX 30` and `refresh_lock()` to extend the TTL; `release_lock()` for clean shutdown
- [x] 1.3 Implement `run_scheduler()` async loop: attempt lock acquisition each cycle, run `promote_due_tasks()` if lock held, refresh lock, sleep for `SCHEDULER_INTERVAL` (default 30s from env var); catch and log all exceptions per cycle without crashing

## 2. Backend Integration

- [x] 2.1 Start the scheduler as `asyncio.create_task()` in the FastAPI `lifespan` startup (after `init_valkey()`), cancel it and release the lock during shutdown

## 3. Tests

- [x] 3.1 Add unit tests for `promote_due_tasks()`: task with past `execute_at` is promoted to pending; task with future `execute_at` is not promoted; task with null `execute_at` is not promoted; only `scheduled`-status tasks are promoted; multiple due tasks promoted in one cycle
- [x] 3.2 Add unit tests for lock functions: `acquire_lock()` succeeds when no lock exists; `acquire_lock()` fails when lock is held; `refresh_lock()` extends TTL; `release_lock()` deletes the lock
- [x] 3.3 Add unit test for WebSocket event: promoted task triggers `task_updated` event with full task payload
- [x] 3.4 Add unit test for scheduler resilience: database error during promotion is caught and logged; Valkey error during lock acquisition is caught and logged
