## MODIFIED Requirements

### Requirement: Tunable settings honour env → DB → default resolution order

`TaskManager._update_concurrency_setting` SHALL resolve `max_concurrent_tasks`, `task_log_buffer_max_entries`, and `task_log_buffer_ttl_seconds` using the canonical `settings_registry` per-key resolver (env → DB → default), so that the values applied at runtime always match what `GET /api/settings` reports as active for those keys.

The task manager SHALL batch-read the three DB rows once per poll cycle and pass them to the resolver via the `db_rows` argument, so per-key resolution does not cost an extra DB round-trip.

The `max(1, ...)` clamp on `task_log_buffer_max_entries` and `task_log_buffer_ttl_seconds` SHALL remain in the task manager (a Valkey `LTRIM`/`EXPIRE` invariant), applied after resolution.

When the resolved value differs from the in-memory cached value, the task manager SHALL log at info level including the new value's source (e.g. `"max_concurrent_tasks: 3 -> 7 (source=env)"`).

#### Scenario: Env var wins over stale DB row

- **WHEN** `MAX_CONCURRENT_TASKS=7` is set in the deployment and the DB row `max_concurrent_tasks` is `"4"`
- **THEN** after the next poll cycle the task manager's semaphore size is `7`

#### Scenario: DB row is used when env is unset

- **WHEN** `MAX_CONCURRENT_TASKS` is unset and the DB row is `"5"`
- **THEN** after the next poll cycle the task manager's semaphore size is `5`

#### Scenario: Default applies when both env and DB are absent

- **WHEN** neither `MAX_CONCURRENT_TASKS` nor the DB row exists
- **THEN** the task manager's semaphore size matches `SETTINGS_REGISTRY["max_concurrent_tasks"]["default"]`

#### Scenario: Buffer settings clamped after resolution

- **WHEN** the resolver returns `0` for `task_log_buffer_max_entries`
- **THEN** the task manager clamps the value to `1` before applying it

#### Scenario: Source is logged on change

- **WHEN** an env-sourced value changes the active `max_concurrent_tasks`
- **THEN** the info-level log line includes `source=env`
