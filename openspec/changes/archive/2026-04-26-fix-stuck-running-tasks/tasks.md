## 1. CancelledError Handler

- [x] 1.1 Add `except asyncio.CancelledError` handler in `_run_task` (task_manager.py) between `except GitSkillsError` and `except Exception` that calls `_schedule_retry` then re-raises
- [x] 1.2 Wrap the `_schedule_retry` call in the CancelledError handler with a try/except to handle DB failures during shutdown

## 2. Orphaned Task Recovery

- [x] 2.1 Convert `_recover_orphaned_task` from a sync function using `asyncio.run()` to an `async` function
- [x] 2.2 Convert `cleanup_orphaned_jobs` to an async function, wrapping synchronous K8s API calls in `asyncio.to_thread()`
- [x] 2.3 Update the call site in `task_manager.py` startup to `await cleanup_orphaned_jobs()`

## 3. Testing

- [x] 3.1 Add test for CancelledError handler — verify `_schedule_retry` is called and CancelledError is re-raised
- [x] 3.2 Add test for CancelledError handler when `_schedule_retry` fails — verify exception is logged and CancelledError still re-raised
- [x] 3.3 Run full backend test suite to verify no regressions
