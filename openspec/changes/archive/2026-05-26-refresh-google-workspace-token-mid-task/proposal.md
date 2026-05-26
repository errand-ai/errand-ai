## Why

Long-running tasks fail with HTTP 401 from Google APIs when the `GOOGLE_WORKSPACE_CLI_TOKEN` injected at task start expires mid-task. Google access tokens have a 60-minute TTL, but errand-server only refreshes the cached credential when it is within 5 minutes of expiry at the moment a task is dequeued — so a task can start with as little as 6 minutes of token life, or with ~50 minutes (as observed in production: a 59.7-minute "job hunt" task ran with a token that had ~49 minutes of life and started failing at the 49-minute mark). Because the task-runner has no elapsed-time limit (only a max-turns cap), even pre-emptively widening the refresh buffer cannot guarantee the token outlives the task. The runner needs the ability to refresh the token while a task is in flight.

## What Changes

- Add a new HTTP endpoint on errand-server (`POST /api/google/refresh-token`, authenticated by a per-task opaque bearer token stored in Valkey under `google_refresh_token:<bearer>` → `<task_id>` — NOT the global `mcp_api_key`, which would be readable by every task via `/workspace/mcp.json`) that refreshes the stored `google_drive` credential by calling `cloud_storage.refresh_token_if_needed` with a zero-second buffer (i.e. force a refresh regardless of remaining lifetime), persists the new credential, and returns the new `access_token` to the caller.
- Wrap the task-runner's `execute_command` function tool so that after each invocation it scans the combined stdout+stderr for the gws "expired token" signature (the literal `"status": "UNAUTHENTICATED"` JSON field, accompanied by `"code": 401` / `"reason": "authError"`). On detection, the wrapper SHALL call the new errand endpoint to obtain a fresh token, replace `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]`, and re-run the exact same command once. The retried output replaces the original output returned to the LLM. The LLM SHALL NOT see the original failure.
- Guard the refresh + retry with an `asyncio.Lock` so two concurrent `execute_command` calls hitting an expired token cause at most one refresh round-trip.
- Cap recovery at one retry per `execute_command` invocation. If the retry still produces an `UNAUTHENTICATED` response, return the second failure to the LLM unchanged.
- Refresh only runs if `GOOGLE_WORKSPACE_CLI_TOKEN` was injected at task start (i.e. the task has Google credentials at all). Tasks without Google Workspace remain unaffected.
- The new errand endpoint is reachable from inside the runner via two new env vars — `ERRAND_API_URL` (the errand server base URL, derived server-side by stripping the `/mcp/...` suffix from `ERRAND_MCP_URL`) and `ERRAND_API_KEY` (a freshly-generated per-task opaque bearer, stored in Valkey at `google_refresh_token:<bearer>` → `<task_id>` with an 8-hour TTL). The bearer-auth scheme reuses the existing `RESULT_CALLBACK_TOKEN` pattern; no new networking surface.

## Capabilities

### New Capabilities
*(none — this extends an existing capability)*

### Modified Capabilities
- `google-workspace-integration`: adds requirements for mid-task token refresh — the task-runner-side detect-and-retry behaviour, the errand-side refresh endpoint, the concurrency lock, and the one-retry cap.

## Impact

**Code**
- `errand/auth_routes.py` or a new `errand/google_routes.py`: new `POST /api/google/refresh-token` endpoint, authenticated via a per-task opaque bearer stored in Valkey (NOT `mcp_api_key`, which is readable by every task with errand MCP enabled).
- `errand/cloud_storage.py`: extend `refresh_token_if_needed` (or add a sibling `force_refresh`) so the buffer is overridable. Optional.
- `task-runner/main.py`: wrap `execute_command` (or its impl) with the detection + retry shim. Add an `asyncio.Lock` and an HTTP client helper that hits `${ERRAND_BASE_URL}/api/google/refresh-token` with `Authorization: Bearer ${MCP_API_KEY}`.
- `task-runner/main.py`: emit a new `token_refreshed` event (alongside existing `tool_call` / `tool_result` events) so refresh activity is visible in task transcripts.

**Configuration**
- Two new env vars injected onto the task-runner container alongside `GOOGLE_WORKSPACE_CLI_TOKEN`: `ERRAND_API_URL` (derived from `ERRAND_MCP_URL`) and `ERRAND_API_KEY` (a freshly-generated per-task bearer stored in Valkey). Both are skipped when no Google credentials are present, so runners without Google Workspace see no new env.
- No new errand settings. The auth credential is the per-task bearer (`secrets.token_hex(32)`), stored in Valkey under `google_refresh_token:<bearer>` → `<task_id>` with an 8-hour TTL — modelled on `RESULT_CALLBACK_TOKEN`.

**Observability**
- New log line on the server when the refresh endpoint is called (task identifier, success/failure).
- New runner event `token_refreshed` plumbed through the existing event-emission pipeline.

**Out of scope**
- OneDrive mid-task refresh (the OneDrive token is consumed via an MCP `Authorization` header, not an env var, so the same mechanism doesn't apply — addressed in a separate future change).
- Pre-flight widening of the refresh buffer at task start (Fix #1 from exploration): rejected because the task-runner has no elapsed-time cap, so no buffer width can guarantee the token outlives an arbitrarily long task.
- LLM-visible refresh tool (i.e. exposing `refresh_google_workspace_token` as an MCP tool the model can call): not added; refresh is fully transparent to the model.
