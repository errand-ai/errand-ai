## Context

Five production bugs and one security flaw were identified in a code review (GitHub #112). The affected modules are:

- `webhook_receiver.py`: dispatches webhook processing via bare `asyncio.create_task`, discarding the reference and any exceptions.
- `scheduler.py`: `release_lock` unconditionally deletes the Valkey/Redis lock key without verifying it still belongs to the calling replica.
- `task_manager.py`: dequeued ORM task objects are used after their source session is closed; `_resolve_provider_sync` creates a new SQLAlchemy engine on every call.
- `cloud_auth_jwt.py`: the JWT issuer is extracted from an unverified token and used directly to fetch JWKS — an attacker can point it at a server they control.
- `main.py`, `task_manager.py`, `scheduler.py`, `zombie_cleanup.py`: each has its own copy of `_next_position`.

## Goals / Non-Goals

**Goals:**
- Fix B1, B3, B4, B5, S3 as described in the proposal.
- Extract shared `_next_position` helper into `errand/utils.py` (Q1).
- All changes are backward-compatible; no API or schema changes.

**Non-Goals:**
- CORS wildcard (S1), SSE token in query string (S5), in-memory dedup across replicas (B2), plaintext SSH key (A1), LRU cache for LLM clients (A2), or any other findings from #112.
- Pydantic-typed request bodies, monolith refactor, or other quality items beyond Q1.

## Decisions

### B1 — Track asyncio tasks in webhook_receiver

**Decision**: Store each `asyncio.create_task(...)` result in a `set` on the receiver instance. Attach a `done_callback` that removes the task from the set and logs any exception at `ERROR` level.

**Why**: Dropping the task reference lets Python GC it before it completes and silently swallows exceptions. A module-level or instance-level set is the standard pattern for fire-and-keep tasks. A callback (vs `await`) preserves the non-blocking dispatch model.

**Alternative considered**: Switch to a task queue (e.g. asyncio.Queue + worker loop). Rejected — introduces more complexity than the bug warrants; existing dispatch semantics are fine.

### B3 — Conditional lock release in scheduler

**Decision**: Before deleting the lock key, check that its value matches the current holder's identity (replica ID / lock token). Use a Lua script (`EVAL`) for atomic check-and-delete.

**Why**: Redis/Valkey `GET` + `DEL` is a TOCTOU race. A Lua script executes atomically server-side. This is the canonical safe lock release pattern.

**Alternative considered**: Use `SET NX PX` with a TTL and let the key expire naturally. Rejected — locks are already TTL-protected; the bug is the explicit `release_lock` call overwriting a new holder's lock mid-run.

### B4 — Copy task data before spawning in task_manager

**Decision**: After dequeuing, load all needed scalar fields from the ORM object into a plain dataclass or dict while the session is still open. Pass the plain object to the processing coroutine; do not pass the ORM instance.

**Why**: SQLAlchemy lazy-loads attributes via the session. After the session closes, any attribute access raises `DetachedInstanceError`. Expunging (`session.expunge(obj)`) before closing is an alternative but copying to a plain struct is safer and makes the data contract explicit.

**Alternative considered**: Keep the session open for the lifetime of the task. Rejected — sessions are not concurrency-safe and holding them open during long task execution leaks connections.

### B5 — Cache sync engine in task_manager

**Decision**: Create the sync engine once at module import time (or lazily on first call with a module-level variable) and reuse it.

**Why**: Each `create_engine` call creates a new connection pool. In the current code, `_resolve_provider_sync` is called repeatedly, creating a new pool each time and never disposing it. Module-level caching is the standard SQLAlchemy pattern.

**Alternative considered**: Pass the engine as a parameter. Rejected — over-engineering for an internal helper; module-level is consistent with how `async_engine` is handled elsewhere.

### S3 — Validate JWT issuer before JWKS fetch

**Decision**: Before calling the JWKS endpoint, assert that `payload["iss"]` matches the configured cloud Keycloak realm URL (from env var or config). Raise `AuthError` if it does not match.

**Why**: The current code trusts the issuer from the unverified token. An attacker crafts a JWT with `iss` pointing to their own OIDC server, passes JWKS verification, and gains access. Pinning the issuer to a known value closes the vector.

**Configuration**: The allowed issuer should come from an existing env var (e.g. `CLOUD_KEYCLOAK_URL` / realm URL) — not a new setting.

### Q1 — Extract _next_position to errand/utils.py

**Decision**: Create `errand/utils.py` with a single `_next_position(session, parent_id)` function. Update all four call sites to import from `utils`.

**Why**: Four divergent copies create maintenance risk. A shared module is the minimal fix.

## Risks / Trade-offs

- **B3 Lua script** — requires Valkey/Redis server ≥ 2.6 (Lua scripting). This is a non-issue for all supported deployments. Risk: negligible.
- **B4 plain struct** — introduces a thin data-transfer object; must keep in sync with ORM model if fields are added. Risk: low; the struct is internal and co-located.
- **S3 issuer pin** — if `CLOUD_KEYCLOAK_URL` is misconfigured, cloud auth breaks completely. Risk: mitigated by existing smoke tests and the fact that the env var is already required for other reasons.
- **Q1 import refactor** — mechanical change across 4 files; low risk of breakage, covered by existing tests.

## Migration Plan

1. Apply code changes on a feature branch (no DB migrations, no config changes except verifying `CLOUD_KEYCLOAK_URL` is set).
2. Run existing test suite — no new infrastructure required.
3. Deploy via normal PR → CI → ArgoCD flow.
4. Rollback: revert the branch; no state changes to undo.

## Open Questions

- None. All decisions are resolved.
