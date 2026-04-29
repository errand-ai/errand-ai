## Context

The codebase has three distinct LLM call sites with different latency profiles, but only one of them honours a configurable timeout:

| Call site | File | Current timeout source |
|---|---|---|
| Title generation (server, sync per task creation) | `errand/llm.py:generate_title` | `llm_timeout` setting (default 30s) |
| Transcription (server, sync per audio note) | `errand/llm.py` (transcription path) | Hard-coded / SDK default |
| Task-runner agent loop (in-container, streaming) | `task-runner/main.py:1262` | OpenAI SDK default (~600s) — never user-configurable |

Settings UI shows one generic "LLM Timeout" input on the Task Management page next to the three model selectors. Users reasonably believe it applies globally; in fact it is bound to a single call site.

Task profiles already let admins override `model`, `system_prompt`, `max_turns`, `reasoning_effort`, and three list fields. They cannot override timeout, even though that is the most model-specific tuning knob (a slow local LM Studio instance with cold-load latency needs minutes, while a hosted API needs seconds).

## Goals / Non-Goals

**Goals:**
- Make each settings-page timeout input unambiguously bound to a specific model role (title / default / transcription).
- Give admins a way to set per-profile timeouts via the same inherit/override pattern already used for `max_turns` and `reasoning_effort`.
- Make the task-runner's `AsyncOpenAI` client honour the resolved timeout, instead of silently falling back to the SDK default.
- Migrate existing `llm_timeout` DB rows so deployments do not silently lose configuration.

**Non-Goals:**
- No change to the providers, model resolution, or LLM client pool.
- No change to streaming-related sub-timeouts (httpx connect / pool / write). Only the overall request timeout is configurable.
- No new top-level settings sub-page; the relocation stays inside Task Management.
- No retry / backoff policy work.
- No change to compaction or probe timeouts (separate, intentional, already env-driven).

## Decisions

### D1: Rename `llm_timeout` to `title_generation_timeout`

The new key tightly couples the value to its actual call site. The old key was misleading.

**Alternatives considered:**
- Keep `llm_timeout` and treat it as the title-generation timeout in docs. Rejected: documentation cannot fix a misleading key shown directly in JSON responses and the Settings UI.
- Use `llm_timeout_title` as a prefix-style key. Rejected: inconsistent with sibling keys (`llm_model` → `task_processing_model`, `transcription_model`); the existing convention is per-role keys, not prefix.

The new keys form a coherent triple aligned with the existing model-setting keys:

| Model setting | Timeout setting (new) |
|---|---|
| `llm_model` | `title_generation_timeout` |
| `task_processing_model` | `task_processing_timeout` |
| `transcription_model` | `transcription_timeout` |

All three default to `30` seconds (matching the current `llm_timeout` default).

### D2: Data migration renames the existing settings row

A single Alembic migration runs:
```sql
UPDATE settings SET key = 'title_generation_timeout' WHERE key = 'llm_timeout';
```
plus an `op.add_column("task_profiles", sa.Column("llm_timeout", sa.Integer, nullable=True))`.

`SETTINGS_REGISTRY` removes `llm_timeout` and adds the three new keys. Settings resolution does not need backwards-compat fallback because the migration runs before app start.

**Alternatives considered:**
- Leave `llm_timeout` in the registry as an alias. Rejected: keeps the misleading name alive and forces resolution code to deal with two keys for the same value forever.

### D3: Per-profile override is a single nullable integer column

`task_profiles.llm_timeout INTEGER NULL`. This mirrors the storage shape of the existing `max_turns` and `reasoning_effort` columns: `NULL` = inherit; non-null = override.

The override applies to **the task-processing model only** — title generation and transcription are server-side, not per-task, so a profile cannot meaningfully override them. The column name `llm_timeout` is acceptably scoped because `TaskProfile` only ever drives the task-runner LLM call.

**Alternatives considered:**
- Per-profile overrides for all three timeouts. Rejected: title generation and transcription are not in the per-task hot path, and bloating the profile model for hypothetical use is premature.

### D4: Resolution chain for the per-task timeout

Resolution at task dispatch time:
1. If `profile.llm_timeout` is non-null → use it.
2. Else use the global `task_processing_timeout` setting.
3. Else fall back to the built-in default (`30`).

This is the same chain pattern the worker already uses for `max_turns` and `reasoning_effort`.

### D5: Plumb the timeout into the task-runner via a new env var

The task manager sets `LLM_REQUEST_TIMEOUT` on the runner container. The runner reads it and passes it to `AsyncOpenAI(..., timeout=float(env))` at `task-runner/main.py:1262`. Validation: parse as float, accept positive values, fall back to SDK default with a warning if parse fails.

**Alternatives considered:**
- Reuse `COMMAND_TIMEOUT` or another existing env var. Rejected: those are unrelated knobs and conflating them risks future bugs.
- Construct the OpenAI client with a full `httpx.Timeout(...)` object. Rejected: the SDK `timeout=<float>` form is documented and simpler; tuning sub-timeouts (connect/read/pool) is out of scope.

### D6: Settings UI relocation

The Task Management page's "LLM Models" section is restructured so each model selector and its companion timeout input render as a single labelled group:

```
┌─ LLM Models ─────────────────────────────────────┐
│ Title generation                                 │
│   Model:   [provider ▼] [model ▼]               │
│   Timeout: [   30 ] seconds                     │
│                                                  │
│ Default task processing                          │
│   Model:   [provider ▼] [model ▼]               │
│   Timeout: [   30 ] seconds                     │
│                                                  │
│ Transcription                                    │
│   Model:   [provider ▼] [model ▼]               │
│   Timeout: [   30 ] seconds                     │
└──────────────────────────────────────────────────┘
```

The single legacy generic timeout input is removed.

### D7: Task profile editor adds a timeout field

The profile editor adds a "LLM Timeout" input next to "Max Turns" and "Reasoning Effort" — using the same blank-to-inherit pattern (empty input ⇒ `null` ⇒ inherit). Validation: positive integer when non-blank.

## Risks / Trade-offs

- **[Risk] Existing deployments use the old `llm_timeout` key in API consumers / scripts** → Migration covers DB. We document the rename in the change PR. No external API surfaces this key (only `/api/settings`).
- **[Risk] A LiteLLM proxy or upstream timeout closes the connection before the runner-side timeout** → Out of scope; we only fix the runner-side knob. We document in `CLAUDE.md` that intermediate proxies have their own timeouts.
- **[Risk] Float-vs-int representation drift between settings (int seconds) and `httpx.Timeout` (float seconds)** → The runner casts to `float`. Settings store integer seconds; UI input is integer.
- **[Risk] A profile with a very large timeout could leave a hung runner pod blocking concurrency** → Existing `max_turns` and pod-level guard rails (Job activeDeadlineSeconds at the K8s layer, configured separately) bound runaway runs; the LLM timeout is per-request, not whole-job.
- **[Trade-off] We do not split `llm_timeout` on the profile into separate per-call-site fields** → Title/transcription are not per-task, so a profile-level setting would not be exercised. Keeping it single-valued matches actual usage.

## Migration Plan

1. Bump `VERSION` (MINOR — additive features + breaking settings key rename for an internal key).
2. Run the Alembic migration:
   - Add `task_profiles.llm_timeout` (nullable integer).
   - `UPDATE settings SET key = 'title_generation_timeout' WHERE key = 'llm_timeout';`
3. Backend: update `SETTINGS_REGISTRY`, rename helper to `_get_title_generation_timeout`, add `_get_task_processing_timeout` and `_get_transcription_timeout` helpers (all reading the new keys).
4. Backend: extend task-profile pydantic schemas + CRUD to accept `llm_timeout` with positive-integer validation.
5. Backend: in `task_manager.py`, resolve the effective timeout per task and set `LLM_REQUEST_TIMEOUT` in `env_vars`.
6. Task-runner: read `LLM_REQUEST_TIMEOUT` and pass to `AsyncOpenAI(..., timeout=...)`.
7. Frontend: rebuild the Task Management page model section to render three (model + timeout) groups; update API payload key on save.
8. Frontend: add timeout input to the profile editor with inherit/override semantics.
9. Tests: update existing `test_llm.py` fixtures (key rename); add tests for the two new helpers; add task-profile tests for the new column + validation; add a task-manager test that the env var is propagated; add a task-runner test that the env var is honoured.
10. Update `CLAUDE.md` and the existing `llm-integration` spec.

**Rollback strategy:** the migration is reversible (`alembic downgrade -1`) — drops the new column and renames the settings key back. The renamed Python helpers can stay as aliases on rollback, but the simpler approach is `git revert` of the merge commit since this is a coherent slice.

## Open Questions

_None._ All design decisions above are committed.
