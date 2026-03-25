## 1. Add TCP keepalive to advisory lock connection

- [x] 1.1 In `TaskManager._acquire_leader_lock`, pass TCP keepalive parameters (`keepalives=1`, `keepalives_idle=10`, `keepalives_interval=10`, `keepalives_count=3`) via `connect_args` when creating the sync engine with `create_sync_engine`
- [x] 1.2 Change the `logger.debug("Another replica holds the leader lock, waiting...")` call to `logger.info`

## 2. Tests

- [x] 2.1 Add a unit test verifying that the sync engine is created with the expected TCP keepalive `connect_args`
- [x] 2.2 Add a unit test verifying the lock-wait message is logged at INFO level when `pg_try_advisory_lock` returns False
