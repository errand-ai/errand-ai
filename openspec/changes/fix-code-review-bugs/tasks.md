## 1. Shared Utility Module (Q1)

- [ ] 1.1 Create `errand/utils.py` with `_next_position(session, parent_id)` function
- [ ] 1.2 Remove local `_next_position` from `errand/task_manager.py` and import from `errand.utils`
- [ ] 1.3 Remove local `_next_position` from `errand/scheduler.py` and import from `errand.utils`
- [ ] 1.4 Remove local `_next_position` from `errand/zombie_cleanup.py` and import from `errand.utils`
- [ ] 1.5 Remove local `_next_position` from `errand/main.py` and import from `errand.utils`

## 2. Webhook Receiver — Tracked Task Dispatch (B1)

- [ ] 2.1 Add `self._background_tasks: set[asyncio.Task]` instance attribute to the webhook receiver class
- [ ] 2.2 Wrap each `asyncio.create_task(...)` call to store the result in `_background_tasks`
- [ ] 2.3 Register a `done_callback` on each task that removes it from the set and logs exceptions at ERROR level

## 3. Scheduler — Conditional Lock Release (B3)

- [ ] 3.1 Write a Lua script for atomic check-and-delete: check lock value equals holder identity, then DEL
- [ ] 3.2 Replace the unconditional `DEL` in `release_lock` with an `EVAL` call using the Lua script
- [ ] 3.3 Verify the lock holder identity value (hostname/token) is stored on lock acquisition and passed to release

## 4. Task Manager — Session Safety (B4)

- [ ] 4.1 Define a plain dataclass (or TypedDict) to hold the task fields needed by the processing coroutine
- [ ] 4.2 In `_dequeue_task`, populate the dataclass from the ORM object while the session is open
- [ ] 4.3 Pass the plain dataclass (not the ORM instance) to the spawned processing coroutine
- [ ] 4.4 Update the processing coroutine to accept the plain dataclass parameter

## 5. Task Manager — Cached Sync Engine (B5)

- [ ] 5.1 Add a module-level variable `_sync_engine = None` in `errand/task_manager.py`
- [ ] 5.2 Update `_resolve_provider_sync` to initialise `_sync_engine` on first call and reuse it on subsequent calls

## 6. Cloud Auth — JWT Issuer Validation (S3)

- [ ] 6.1 Identify where the expected cloud Keycloak realm URL is configured (env var / setting)
- [ ] 6.2 In `validate_cloud_jwt` (`errand/cloud_auth_jwt.py`), decode the token without verification to extract `iss`
- [ ] 6.3 Assert `iss` matches the configured realm URL; raise `AuthError` immediately if not
- [ ] 6.4 Only proceed to JWKS fetch if issuer validation passes

## 7. Tests & Verification

- [ ] 7.1 Add/update unit tests for `_next_position` in `errand/utils.py`
- [ ] 7.2 Add unit test: webhook dispatch task reference kept, exception callback logs error
- [ ] 7.3 Add unit test: scheduler `release_lock` is a no-op when lock value does not match
- [ ] 7.4 Add unit test: task manager processing coroutine receives plain dataclass, not ORM instance
- [ ] 7.5 Add unit test: `_resolve_provider_sync` calls `create_sync_engine` only once across multiple calls
- [ ] 7.6 Add unit test: `validate_cloud_jwt` raises `AuthError` for mismatched issuer without making HTTP call
- [ ] 7.7 Run full test suite (`DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`) and confirm all tests pass
