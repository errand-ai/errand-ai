## Context

The task processing coroutine `_run_task` in `task_manager.py` has this exception structure:

```python
async with self._semaphore:
    try:
        exit_code, stdout, stderr = await self._process_task(...)
        if parsed_ok:
            # move to completed/review
        else:
            logger.warning("container exited with code %d", exit_code)  # ← logged
            await self._schedule_retry(task, ...)                       # ← never reached
    except GitSkillsError:
        ...
    except Exception:
        await self._schedule_retry(task)
    finally:
        cancel heartbeat
```

`asyncio.CancelledError` inherits from `BaseException` (not `Exception`) in Python 3.9+, so it bypasses all handlers. The task stays "running" in the DB.

Separately, `cleanup_orphaned_jobs` in `container_runtime.py` calls `_recover_orphaned_task` which uses `asyncio.run()` inside the existing uvicorn event loop, causing a RuntimeError.

## Goals / Non-Goals

**Goals:**
- Tasks never stay stuck in "running" when their container is gone
- Orphaned task recovery works during K8s startup cleanup
- Both fixes are safe during normal operation (no false positives)

**Non-Goals:**
- Changing the retry backoff strategy
- Changing the zombie cleanup interval or timeout

## Decisions

### D1: Catch CancelledError, schedule retry, then re-raise

**Decision**: Add `except asyncio.CancelledError` before `except Exception` in `_run_task`. The handler calls `_schedule_retry`, then re-raises the CancelledError so the coroutine properly cancels.

```python
except asyncio.CancelledError:
    logger.warning("Task %s processing cancelled, scheduling retry", task.id)
    try:
        await self._schedule_retry(task, output="Processing cancelled during shutdown")
    except Exception:
        logger.exception("Failed to schedule retry for cancelled task %s", task.id)
    raise
```

The inner try/except is necessary because the cancellation may be due to the DB connection being closed — `_schedule_retry` itself could fail. In that case, the zombie cleanup (which runs on the next startup) will catch it.

**Rationale**: Re-raising CancelledError preserves the standard asyncio cancellation semantics. The retry is best-effort — if it fails, the zombie cleanup is the safety net.

### D2: Make _recover_orphaned_task async

**Decision**: Convert `_recover_orphaned_task` to an `async` function and call it with `await` from `cleanup_orphaned_jobs`. Since `cleanup_orphaned_jobs` is called during FastAPI startup (lifespan), it already runs inside the event loop and can be made async.

The K8s API calls in `cleanup_orphaned_jobs` use the synchronous kubernetes client. These will be wrapped in `asyncio.to_thread()` or the function can remain partially sync with the DB recovery part awaited separately.

**Rationale**: `asyncio.run()` cannot be used inside an already-running event loop. The simplest fix is to make the caller async and await the recovery coroutine directly.

## Risks / Trade-offs

**[Risk] CancelledError handler's _schedule_retry may also fail** → Mitigated by the inner try/except and the zombie cleanup safety net. The zombie cleanup runs every 60s and catches tasks with stale heartbeats.

**[Risk] Making cleanup_orphaned_jobs async changes its call site** → The function is called from FastAPI lifespan startup, which is already async. Minimal impact.
