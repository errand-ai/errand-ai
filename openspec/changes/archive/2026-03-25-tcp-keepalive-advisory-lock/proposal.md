## Why

The TaskManager's leader election uses a Postgres advisory lock held via a sync `raw_connection()`. When a pod is killed (e.g. SIGKILL during rolling update), this connection is not closed cleanly, and Postgres continues to consider it alive until TCP keepalive detects the dead peer. With default OS/Postgres TCP settings this can take hours, during which the new pod's `pg_try_advisory_lock` returns `False` every poll cycle and no tasks are processed. This was observed in production on 2026-03-24 where the current pod ran for 12+ hours without processing any pending tasks because a stale connection from a killed pod still held the advisory lock.

## What Changes

- Add TCP keepalive options (`keepalives=1`, `keepalives_idle`, `keepalives_interval`, `keepalives_count`) to the sync engine connection used for the advisory lock in `TaskManager._acquire_leader_lock`, so Postgres detects dead connections within ~30 seconds instead of hours.
- Raise the log level of the "Another replica holds the leader lock" message from `DEBUG` to `INFO` so lock contention is visible in production logs without enabling debug logging.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-manager`: The advisory lock connection requirements change to include TCP keepalive parameters, and the lock-wait log message changes from DEBUG to INFO.

## Impact

- **Code**: `errand/task_manager.py` — `_acquire_leader_lock` method (sync engine creation and logging)
- **No new dependencies**: TCP keepalive is configured via libpq connection parameters already supported by psycopg2/asyncpg
- **No API changes**: Internal background task behavior only
- **No migrations**: No database schema changes
