## Why

`TaskManager._update_concurrency_setting` (in `errand/task_manager.py`) reads tunable settings — `max_concurrent_tasks`, `task_log_buffer_max_entries`, `task_log_buffer_ttl_seconds` — directly from the `settings` DB table and only falls back to environment variables when the DB row is missing. The canonical resolution order, defined by `settings_registry.resolve_settings`, is **env → DB → default**: env-sourced values are reported with `source: "env"` and `readonly: true` by `/api/settings`, and the admin UI greys them out so the operator believes the env var is authoritative.

The two paths disagree. If a `MAX_CONCURRENT_TASKS` env var is set on a deployment that also has a stale `max_concurrent_tasks` DB row (e.g. from an earlier UI save before the env override was added to the Helm values), the task manager silently uses the DB value, while `/api/settings` and the UI show the env value as the active one. The same trap applies to any future tunable read this way.

Copilot flagged this on PR #171 (`task_manager.py:1101` thread, deliberately left open). Fixing it here keeps the behaviour shift reviewable in isolation rather than bundling it into an unrelated feature change.

## What Changes

- Introduce a shared resolver in `settings_registry` (e.g. `resolve_setting_value(session, key) -> tuple[value, source]`) that applies the canonical **env → DB → default** order for a single key, mirroring `resolve_settings` but without the masking/metadata. Coerce the result via the registry's known type (int / str / dict) so callers don't reimplement parsing.
- Refactor `TaskManager._update_concurrency_setting` to use the new helper for `max_concurrent_tasks`, `task_log_buffer_max_entries`, and `task_log_buffer_ttl_seconds`. Drop the bespoke env-fallback branch and the now-redundant defaulting.
- Refactor `resolve_settings` in `settings_registry` to delegate per-key resolution to the same helper so `/api/settings` and the task manager share one code path. The masking + `readonly` metadata stays in `resolve_settings`.
- Add tests covering: env-only, DB-only, env-overrides-DB (the regression we're fixing), default-only, and clamping for the buffer settings.

Behaviour change: a deployment that previously relied on a stale DB row winning over an env var will see the env value take effect after upgrade. This is an intentional alignment with the documented resolution order, but operators with both set on the same key should be flagged in release notes so they can pick one source.

## Capabilities

### New Capabilities

(none — this is an alignment fix in an existing capability)

### Modified Capabilities

- `task-manager`: clarify that runtime-tunable settings (`max_concurrent_tasks`, `task_log_buffer_max_entries`, `task_log_buffer_ttl_seconds`) MUST be resolved using the `env → DB → default` order, matching `resolve_settings`.
- `settings-registry`: factor out the per-key resolution path so `resolve_settings` and direct consumers share it; the API contract of `/api/settings` is unchanged.

## Impact

- **Backend:** new helper in `errand/settings_registry.py`; `errand/task_manager.py` `_update_concurrency_setting` rewritten to use it; `resolve_settings` refactored to delegate.
- **Tests:** `errand/tests/test_task_manager.py` concurrency-resolution tests rewritten around the new helper; new `errand/tests/test_settings_registry.py` cases for the resolver matrix.
- **API / schema / migrations:** none. `/api/settings` payload shape is unchanged.
- **Operator-visible behaviour change:** env vars now beat DB rows for the three keys above (matches what `/api/settings` already reports). Document in release notes.
- **Auth:** unaffected.
