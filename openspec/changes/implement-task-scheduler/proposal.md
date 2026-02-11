## Why

Tasks categorised as `scheduled` or `repeating` are placed in the `scheduled` status with an `execute_at` time, but nothing currently checks whether that time has arrived and moves them to `pending` for the worker to process. We need a scheduler that periodically promotes due tasks — and it must work correctly when multiple backend replicas are running.

## What Changes

- Add a scheduler loop that runs inside the backend process, checking for tasks in `scheduled` status whose `execute_at` time has passed, and moving them to `pending`
- Use a Valkey distributed lock to ensure only one backend replica runs the scheduler at a time, with automatic failover if the lock holder stops
- Expose a Valkey connection from the existing `events.py` module for reuse by the scheduler
- Add backend tests covering the scheduler loop, lock acquisition, and task promotion logic

## Capabilities

### New Capabilities
- `task-scheduler`: Periodic scheduler that promotes due scheduled tasks to pending status, coordinated across replicas via Valkey distributed lock

### Modified Capabilities
<!-- None — the worker already picks up `pending` tasks; no spec-level behaviour change needed -->

## Impact

- **Backend**: New scheduler module (`scheduler.py`) started alongside the FastAPI app on startup
- **Valkey**: Uses existing Valkey connection (`redis-py`) for distributed lock via `SET NX EX` pattern
- **Database**: No schema changes — uses existing `status`, `execute_at`, and `category` columns on tasks table
- **Helm**: No changes required — scheduler runs in-process within existing backend pods
- **Worker**: No code changes — continues polling for `pending` tasks as before
