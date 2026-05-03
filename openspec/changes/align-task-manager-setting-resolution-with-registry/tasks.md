## 1. Per-key resolver in settings_registry

- [x] 1.1 Add `resolve_setting_value(session, key, *, db_rows=None) -> tuple[Any, str]` coroutine in `errand/settings_registry.py`. Apply env → DB → default. Coerce to the type of the registered default (`int`, `str`, JSON for `dict`/`list`); when default is `None`, return raw. Log + fall back to default on coercion failure.
- [x] 1.2 Add a private `_coerce(raw, default)` helper used by 1.1 so the coercion path is unit-testable in isolation.

## 2. Refactor resolve_settings to delegate

- [x] 2.1 Rewrite `resolve_settings` in `errand/settings_registry.py` so it batch-loads the DB rows once, then calls `resolve_setting_value(session, key, db_rows=...)` for every non-excluded registry key. Keep the masking, `source`, `sensitive`, and `readonly` fields exactly as they were.
- [x] 2.2 Confirm the response shape is byte-identical for an unchanged DB+env state (snapshot test against a known fixture).

## 3. Refactor TaskManager to use the resolver

- [x] 3.1 In `errand/task_manager.py` `_update_concurrency_setting`, batch-load the three DB rows (`max_concurrent_tasks`, `task_log_buffer_max_entries`, `task_log_buffer_ttl_seconds`) into a `db_rows` map and call `resolve_setting_value(session, key, db_rows=db_rows)` for each.
- [x] 3.2 Drop the bespoke env fallback (`os.environ.get("MAX_CONCURRENT_TASKS", ...)`) and the duplicated literal defaults — both are now owned by the resolver.
- [x] 3.3 Keep the `max(1, ...)` clamp on the two buffer settings, applied after resolution.
- [x] 3.4 Update the change-detection log lines to include `source=<env|database|default>` when a value changes at runtime.
- [x] 3.5 Initialise `TaskManager.__init__` defaults via the resolver against an empty session/db_rows so init values match the steady-state code path.

## 4. Tests

- [x] 4.1 New `errand/tests/test_settings_registry.py` (or extend existing) covering the resolver matrix: env-only, DB-only, env-overrides-DB, default-only, empty-string env treated as unset, coercion failure, pre-fetched `db_rows` short-circuit, and the `default is None` raw-return path.
- [x] 4.2 In `errand/tests/test_task_manager.py`, rewrite the existing `_update_concurrency_setting` tests to match the new code path: env-overrides-DB regression test, batch DB read, info log includes source, buffer clamp still applied.
- [x] 4.3 Snapshot test for `GET /api/settings` ensuring the response shape and field names are unchanged for a fixture state.

## 5. Verification

- [x] 5.1 `pytest errand/tests/` — all tests pass locally and in CI.
- [ ] 5.2 Local docker-compose: set `MAX_CONCURRENT_TASKS=7` in `testing/.env`, save a different value via the UI, restart the stack, and confirm the task manager runs with `7` and `/api/settings` reports `source: env, readonly: true`.
- [ ] 5.3 `GET /api/settings` JSON payload diffed pre/post change against the same fixture is identical.

## 6. Documentation and release

- [x] 6.1 Bump `VERSION` per semver — patch (alignment fix; no spec-level change to the API surface).
- [ ] 6.2 Note the operator-visible behaviour change in the PR description: env vars now beat stale DB rows for `max_concurrent_tasks`. Recommend operators with both set on the same key remove one before upgrade.
- [ ] 6.3 PR description references this change directory and links the modified specs (`settings-registry`, `task-manager`).
- [ ] 6.4 Reference and resolve the PR #171 `task_manager.py:1101` review thread that originally flagged this.
