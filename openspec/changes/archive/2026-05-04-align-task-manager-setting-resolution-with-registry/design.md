## Context

Two consumers read the same DB-backed settings table by different paths:

1. `settings_registry.resolve_settings` — used by `GET /api/settings` and the admin UI. Walks the registry, applies **env → DB → default** per key, masks sensitive values, and tags each entry with `source` (`env`/`database`/`default`) and `readonly` (true when env-sourced).
2. `task_manager.TaskManager._update_concurrency_setting` — runs every poll cycle on the leader replica. Reads three keys (`max_concurrent_tasks`, `task_log_buffer_max_entries`, `task_log_buffer_ttl_seconds`) and applies a bespoke order: **DB → env (only as fallback when DB row is missing) → hard-coded default**.

For `max_concurrent_tasks` only, `MAX_CONCURRENT_TASKS` is registered as the env override. For the two buffer keys, no env var is registered and the difference is dormant — but the same shape of bug will appear if either key is given an env var later. The `task_log_buffer_*` keys were added to `_update_concurrency_setting` in the immediately-preceding PR (#171); fixing the inconsistency now keeps the change focused and reviewable.

Today, an operator who:

1. Sets `max_concurrent_tasks` via the UI (writes a DB row), then
2. Deploys with `MAX_CONCURRENT_TASKS=N` in the Helm values (intending to pin the deploy),

sees `/api/settings` report `value: N, source: "env", readonly: true` (so the UI greys the field), while `TaskManager` actually runs with the *DB* value. The disagreement is silent and only surfaces when concurrency behaviour doesn't match what the operator set.

## Goals / Non-Goals

**Goals:**

- Single source of truth for **per-key** resolution: env → DB → default, identical between `/api/settings` and `task_manager`.
- Strongly typed coercion (int/string/dict) driven from the registry, so callers don't reimplement `int(...)` parsing.
- Preserve all existing behaviour of `resolve_settings` that consumers depend on: masking, `source` and `readonly` tags in the response shape are unchanged.
- Tests pin the resolution matrix (env-only, DB-only, env-overrides-DB, default-only, clamp on out-of-range buffer values) so future regressions fail loudly.

**Non-Goals:**

- Rewriting how settings are *written* (the admin POST flow is untouched).
- Adding new settings or new env vars. The set of registered env vars is unchanged.
- Hot-reload semantics or push-based notification. The task manager continues to poll on its existing cadence.
- Changing the `/api/settings` response shape, or the way sensitive values are masked.

## Decisions

### Decision 1: Add a single `resolve_setting_value(session, key) -> tuple[value, source]` helper in `settings_registry`

**Choice:** Introduce a module-level coroutine in `errand/settings_registry.py` that takes an `AsyncSession` and a registry key, and returns a `(value, source)` tuple where `source ∈ {"env", "database", "default"}`. The helper applies env → DB → default and coerces using the registered default's type (`int(...)`, `str(...)`, JSON for dict).

**Rationale:** Sharing one resolver between `resolve_settings` and `_update_concurrency_setting` is the only way to guarantee they can't drift. Keeping it `async` lets the task manager continue using the existing `async_session()` it already owns. Returning the source alongside the value is what `resolve_settings` needs anyway, and lets the task manager log "source=env" when it changes a value at runtime.

**Alternatives considered:**

- *Move all metadata into the registry itself, including coercion functions:* tempting but expands scope. The registry today only stores defaults; introducing coercion functions per-key changes the registry's shape for everyone. We can always do that later if a third consumer appears.
- *Reuse `resolve_settings` from the task manager and key by name:* wasteful — `resolve_settings` materialises every key, masks them, and decorates with metadata. The task manager only wants three keys and doesn't want masking. Sharing the per-key helper is cleaner.

### Decision 2: Coerce types from the registered default's `type(...)`

**Choice:** The helper looks at `type(SETTINGS_REGISTRY[key]["default"])` and applies the matching cast: `int` → `int(raw)`, `str` → `raw`, `dict`/`list` → `json.loads(raw)`. Empty strings/None fall through to the default. Coercion failures (e.g. `int("abc")`) log a warning and return the default with `source="default"`.

**Rationale:** All three task-manager-tunable defaults are `int`, so this collapses to "just `int(raw)`" for the actual fix. Driving from the default type means we don't add new metadata to every registry entry, and the same helper transparently supports the JSON-shaped settings (`mcp_servers`, `litellm_mcp_servers`) that `resolve_settings` already handles.

**Trade-off:** A future setting whose default is `None` (e.g. `mcp_servers: default=None`) needs an explicit type hint or a per-key opt-out. Today those keys are read by `resolve_settings` only and `resolve_settings` returns the raw DB string verbatim — we'll preserve that path by special-casing `default is None` to return the raw value untouched. The new task-manager call sites all have integer defaults, so they're unaffected.

### Decision 3: Clamp per-call site, not in the resolver

**Choice:** The buffer max/ttl clamp (`max(1, value)`) added in PR #171 stays inside `_update_concurrency_setting` rather than moving into the resolver.

**Rationale:** Clamping is a task-manager invariant (Valkey `LTRIM`/`EXPIRE` semantics), not a registry-level rule. Other consumers might legitimately accept 0 (e.g. "disabled"). Keep the resolver pure.

### Decision 4: Behaviour change is intentional and documented

**Choice:** When env and DB both exist, the env wins after this change. We accept the behaviour shift, call it out in the change log, and add release notes asking operators with both sources set for the same key to pick one.

**Rationale:** The current behaviour silently disagrees with what `/api/settings` reports. Aligning with the documented and UI-rendered order (env wins) is the less-surprising default and matches operator expectations.

**Migration footprint:** Only `max_concurrent_tasks` has a registered env var today, so the behaviour change is scoped to deployments that set both `MAX_CONCURRENT_TASKS` and a DB row. In practice that's a handful of deployments at most; the env value is what `/api/settings` already reports as active.

### Decision 5: Refactor `resolve_settings` to delegate per-key

**Choice:** `resolve_settings` keeps its outer shape (loop over registry, mask sensitive, build `{value, source, sensitive, readonly}` dict) but the env/DB/default selection becomes a call to the new helper.

**Rationale:** Two consumers means two code paths means inevitable drift. One path is non-negotiable.

## Risks / Trade-offs

- **Operator-visible regression for deployments relying on DB-overrides-env**: explicit; flagged in release notes; mitigation is to remove the DB row or unset the env var.
- **Per-key DB lookup is a round-trip per key**: today `_update_concurrency_setting` does a single batched query for three keys; the per-key helper would do three. Mitigation: keep the batch in `_update_concurrency_setting` (read all three rows once, pass them as a "row override" to the helper) so we don't regress poll-loop latency. The helper signature accepts an optional pre-fetched DB row map for this case.
- **Coercion failure mode**: a malformed DB row (e.g. `max_concurrent_tasks="abc"`) currently raises and the entire `_update_concurrency_setting` swallows it. After the change, the helper logs a warning and returns the default — slightly different semantics but more graceful. Tests cover this path.
- **Registry-default-is-None path**: handled by the special case in Decision 2; covered by a test.

## Migration Plan

- **Deploy:** rolling restart, no schema changes. The new task-manager resolution takes effect on the next poll cycle of whichever replica becomes leader. Mixed-mode operation during the rollout is safe: every replica is reading the same DB and env, just via slightly different code paths.
- **Backfill:** none.
- **Rollback:** revert the PR. No data shape changes.
- **Operator action:** for the `max_concurrent_tasks` key only, deployments that have both `MAX_CONCURRENT_TASKS` set and a non-matching DB row should remove one of them before the upgrade. Mention in release notes.

## Open Questions

- Should we eventually push the env→DB→default order down into a generic `Setting.resolve(key)` ORM method? Probably yes, but that touches the model and is out of scope here. Captured for follow-up.
