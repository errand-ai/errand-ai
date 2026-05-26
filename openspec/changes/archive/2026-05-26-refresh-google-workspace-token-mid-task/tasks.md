## 1. Server-side: force-refresh helper

- [x] 1.1 In `errand/cloud_storage.py`, add a `force_refresh_token(provider, credentials, session)` helper (or extend `refresh_token_if_needed` with a `force: bool` parameter) that performs the refresh regardless of the 5-minute remaining-life buffer, persists the new credential, and returns the updated credentials dict on success or `None` on failure.
- [x] 1.2 Add unit tests covering: (a) force-refresh succeeds when `expires_at` is far in the future; (b) returns `None` when no refresh token is stored; (c) returns `None` and leaves credentials untouched when the upstream token endpoint returns non-200.

## 2. Server-side: HTTP endpoint

- [x] 2.1 Create `errand/google_routes.py` (or extend an existing routes module) exposing `POST /api/google/refresh-token`.
- [x] 2.2 Add a FastAPI dependency that validates the `Authorization: Bearer <mcp_api_key>` header against the `mcp_api_key` setting. Reject with `401` if missing or mismatched.
- [x] 2.3 In the handler, load the `google_drive` `PlatformCredential`; return `404` if absent.
- [x] 2.4 Call the force-refresh helper from 1.1. On `None`, return `502` with a short error message. On success, return `{ "access_token": "<value>", "expires_at": <int> }`.
- [x] 2.5 Log `task_id` (from header if present), provider, success/failure, and the new `expires_at`. Do not log the access token.
- [x] 2.6 Register the router with the FastAPI app.
- [x] 2.7 Add endpoint tests: 401 unauthorised, 404 no creds, 502 upstream failure, 200 happy path with persisted credential.

## 3. Server-side: inject runner env vars

- [x] 3.1 In `errand/task_manager.py`, when injecting `GOOGLE_WORKSPACE_CLI_TOKEN`, also set `ERRAND_API_URL` (derived from `ERRAND_MCP_URL` by stripping `/mcp/...`) and `ERRAND_API_KEY` (the `mcp_api_key` setting value).
- [x] 3.2 Skip the new env vars if no `mcp_api_key` is configured; log a single warning. (Refresh will then silently no-op in the runner.)
- [x] 3.3 Add a unit test asserting both new env vars are present when Google credentials exist, and absent when they don't.

## 4. Runner-side: refresh helper

- [x] 4.1 In `task-runner/main.py`, add an async helper `_refresh_google_workspace_token() -> str | None` that POSTs to `${ERRAND_API_URL}/api/google/refresh-token` with the bearer header, returns the new `access_token` on success, or `None` on any failure. Use `httpx.AsyncClient` with a 10-second timeout. Never raise.
- [x] 4.2 Add a module-level `asyncio.Lock` named `_google_token_refresh_lock`.
- [x] 4.3 Inside the helper, after acquiring the lock, re-read `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]`; if it differs from the value observed at entry, return that value (assume another caller refreshed concurrently) and skip the network call.
- [x] 4.4 On success, update `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]` with the new token value before releasing the lock.

## 5. Runner-side: wrap `execute_command`

- [x] 5.1 Add a constant `_GWS_AUTH_FAILED_SIGNATURE = '"status": "UNAUTHENTICATED"'`.
- [x] 5.2 In `_execute_command_impl` (or the function-tool body), after capturing combined stdout/stderr, check: signature present AND `GOOGLE_WORKSPACE_CLI_TOKEN` is set in `os.environ` AND no refresh attempted yet in this invocation.
- [x] 5.3 On match, call `_refresh_google_workspace_token()`. If it returns `None`, leave the original output untouched and proceed.
- [x] 5.4 If refresh returned a new token, re-run the exact same subprocess command once with the updated environment.
- [x] 5.5 Return only the retry's output to the caller. Discard the original output.
- [x] 5.6 Cap recovery at one retry per invocation regardless of the retry output.

## 6. Runner-side: emit `token_refreshed` event

- [x] 6.1 Emit `token_refreshed` events via the existing `emit_event()` pipeline. Payload: `{ "provider": "google_workspace", "status": "ok" | "failed" }`. Never include the token.
- [x] 6.2 Emit on every refresh attempt — both branches.
- [x] 6.3 Confirm the events do not enter the LLM conversation history (event emission is stderr-side, not part of the agent loop's tool result).

## 7. Runner-side tests

- [x] 7.1 Test: `execute_command` invocation whose captured output contains the signature triggers exactly one refresh and one retry; only retry output is returned.
- [x] 7.2 Test: signature present but `GOOGLE_WORKSPACE_CLI_TOKEN` unset → no refresh, original output returned.
- [x] 7.3 Test: signature in retry output too → returned unchanged, no second refresh attempted.
- [x] 7.4 Test: refresh endpoint returns non-200 → original output returned, no retry attempted.
- [x] 7.5 Test (concurrency): two coroutines call the wrapper in parallel with auth-failing commands → exactly one HTTP POST to the refresh endpoint; both retries see the new token.
- [x] 7.6 Test: refresh updates `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]` before the retry runs (assert via the env passed to the subprocess).
- [x] 7.7 Test: `token_refreshed` event is emitted on success and on failure with the correct status field.

## 8. Documentation & polish

- [x] 8.1 Update `CLAUDE.md` "Task Processing (TaskManager)" section to note the mid-task refresh path and the two new env vars (`ERRAND_API_URL`, `ERRAND_API_KEY`).
- [x] 8.2 Update Helm chart (`helm/content-manager/`) only if any new ConfigMap / Secret reference is needed — likely no chart changes (both new env vars are derived from existing config).
- [x] 8.3 Bump `VERSION` (MINOR — backwards-compatible feature).

## 9. Verification

- [x] 9.1 From the repo root, run `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v` — all pass. (The path `errand/tests/` is cwd-relative; the env var avoids hitting a real Postgres.)
- [x] 9.2 From the repo root, run `errand/.venv/bin/python -m pytest task-runner/ -v` — all pass.
- [x] 9.3 Run the docker-compose stack and trigger a task that uses `gws`; confirm normal-path behaviour unchanged.
- [x] 9.4 Simulate token expiry locally (e.g. set `GOOGLE_WORKSPACE_CLI_TOKEN` to an obviously-invalid value at task start) and confirm: refresh fires, env var updates, retry succeeds, transcript contains `token_refreshed` event, LLM result reflects only the successful outcome.
- [x] 9.5 Validate OpenSpec change: `openspec status --change refresh-google-workspace-token-mid-task` reports all 4 artifacts complete.
