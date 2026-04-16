## Why

A code review (GitHub issue #112) identified high and medium severity bugs in the webhook receiver, scheduler, task manager, and cloud auth modules — including silent exception loss, race conditions, database session leaks, connection pool exhaustion, and a JWT SSRF vector. These are live correctness and security risks in production.

## What Changes

- **B1**: `webhook_receiver.py` — store `asyncio.create_task` references and attach exception handlers so dispatched webhook tasks are not silently dropped or garbage-collected.
- **B3**: `scheduler.py` — replace unconditional lock delete with conditional delete (only if this holder still owns it) to prevent one replica releasing another's lock.
- **B4**: `task_manager.py` — expunge or copy ORM task data before passing to a spawned processing coroutine so the object is not used after its session closes.
- **B5**: `task_manager.py` — cache the sync engine created in `_resolve_provider_sync` at module level instead of creating a new one on every call, preventing connection pool exhaustion.
- **S3**: `cloud_auth_jwt.py` — validate the JWT issuer against the known Keycloak realm URL before fetching JWKS, eliminating the SSRF/token-forgery vector.
- **Q1**: Extract the duplicated `_next_position` helper from `main.py`, `task_manager.py`, `scheduler.py`, and `zombie_cleanup.py` into a shared `errand/utils.py` utility module.

## Capabilities

### New Capabilities

- `errand-utils`: Shared internal utility module (`errand/utils.py`) providing common helpers (e.g. `_next_position`) used across task manager, scheduler, zombie cleanup, and main.

### Modified Capabilities

- `webhook-receiver`: Task dispatch changes from fire-and-forget to tracked tasks with exception handling.
- `task-scheduler`: Lock release becomes conditional (holder-checked) to prevent cross-replica lock clobber.
- `task-manager`: Session lifecycle fix for dequeued tasks; sync engine cached at module level.
- `cloud-auth`: JWT issuer validation added before JWKS fetch to block SSRF token-forgery.

## Impact

- `errand/webhook_receiver.py` — task lifecycle management
- `errand/scheduler.py` — advisory lock release logic
- `errand/task_manager.py` — session handling on dequeue, sync engine lifecycle
- `errand/cloud_auth_jwt.py` — JWT validation flow
- `errand/main.py`, `errand/zombie_cleanup.py` — import from new `errand/utils.py`
- New file: `errand/utils.py`
- No API or database schema changes; no breaking changes
