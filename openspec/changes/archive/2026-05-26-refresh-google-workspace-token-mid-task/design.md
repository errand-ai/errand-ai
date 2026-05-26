## Context

Google Workspace OAuth access tokens have a 60-minute TTL. The task-runner today receives the token as a snapshot `GOOGLE_WORKSPACE_CLI_TOKEN` env var at task start, and that snapshot may already have less than 60 minutes of life when injected — `errand/cloud_storage.py:refresh_token_if_needed` only refreshes if the token is within a 5-minute buffer of expiry, so any value of `expires_at` further away than 5 min is passed through as-is. Task-runner pods have no elapsed-time cap (only `MAX_TURNS`), so any task can in principle outlive its injected token. A real production failure (a 59.7-minute "job hunt" task starting with ~49 minutes of token life) confirms this is not theoretical.

The task-runner already talks back to errand-server in two ways: (a) connecting to the errand MCP server (URL in `ERRAND_MCP_URL`, bearer token = `mcp_api_key` baked into the MCP config file at startup), and (b) posting final results to `RESULT_CALLBACK_URL` with `RESULT_CALLBACK_TOKEN`. There is a clean precedent for injecting URL + bearer-token env-var pairs and using `httpx` for callbacks. Reusing this shape avoids inventing new authentication surface.

The runner's `execute_command` function tool is the only place `gws` is ever invoked from inside a task — gws is a shell binary, the agent calls it via shell. Wrapping `execute_command` is therefore sufficient; there is no second tool surface to also instrument.

## Goals / Non-Goals

**Goals:**
- A long-running task that exhausts its Google access token mid-execution SHALL recover automatically, with the LLM unaware of the failure.
- Refresh logic SHALL be invisible to the agent's conversation history — no extra tool turns, no LLM prompt augmentation, no token values flowing through model context.
- Concurrent `execute_command` calls hitting expired-token responses SHALL deduplicate to a single refresh round-trip.
- A refresh that itself fails (refresh token revoked, errand unreachable) SHALL surface a useful error to the LLM rather than loop or swallow the original failure.
- The new errand endpoint SHALL reuse the existing `mcp_api_key` bearer-token scheme — no new credentials, no new RBAC.

**Non-Goals:**
- OneDrive mid-task token refresh. OneDrive tokens are consumed by an MCP server (header on the connection) not an env var; refresh there requires reconnecting an MCP client mid-stream, which is structurally different. Future change.
- Pre-flight buffer widening. Considered and rejected: without a task-runtime cap, no static buffer width is sufficient.
- Exposing the refresh as an LLM-visible MCP tool. Adds context cost and a failure mode (model forgets / hallucinates the call) for no gain over the transparent wrapper.
- Refreshing tokens for any tool other than `execute_command` (no other tool consumes `GOOGLE_WORKSPACE_CLI_TOKEN` today).
- Backfilling the refresh capability into already-running tasks at deploy time. The wrapper takes effect on the next task that starts under the new image.

## Decisions

### Decision 1: Trigger the refresh from the runner side, not the server side

**Choice:** The runner detects token expiry from the `gws` stderr and initiates the refresh. The server is purely a refresh-on-demand endpoint.

**Alternatives considered:**
- *Server-side proactive refresh on a background timer.* Rejected — does not handle revoked or sooner-than-TTL invalidation, and requires the runner to poll for the new value (or for the server to push it in, which needs container exec — not portable).
- *Server pushes refreshed tokens to running pods.* Rejected — requires the server to know each running pod's address, opens an inbound surface on the runner, more complex than reactive pull.

**Rationale:** Failures are the load-bearing signal — they're definitive (the token genuinely doesn't work), and they're observable in-process without any new coordination. Pull-on-failure beats push-on-schedule for correctness and simplicity.

### Decision 2: Detect via `"status": "UNAUTHENTICATED"` substring match

**Choice:** Treat a command as auth-failed if and only if its captured stdout+stderr contains the literal substring `"status": "UNAUTHENTICATED"`.

**Alternatives considered:**
- *Match on HTTP 401 status code.* Rejected — gws does not surface raw HTTP status codes in a parseable form; the JSON body is more reliable.
- *Match on `reason: "authError"` or `code: 401`.* Either also works, but `UNAUTHENTICATED` is the most semantically specific to expired/invalid OAuth.
- *Match on `error[api]: Request had invalid authentication credentials`.* Could drift if gws localizes or rewords. The structured JSON field is more stable.
- *Modify `gws` to exit with a distinct status code.* Rejected — `gws` is an upstream tool bundled by tag; modifying it is out of scope.
- *Detect from the subprocess exit code.* gws may exit 0 with auth errors in JSON output or exit 1; we don't want to retry every nonzero command.

**Rationale:** `"status": "UNAUTHENTICATED"` is a Google API standard field (Google's API error contract, not gws-specific) and is the most stable signature available. False positives are essentially impossible (it's a structured JSON field name, not a free-form English phrase).

### Decision 3: Wrap `execute_command`, not the agent loop

**Choice:** Add the detection + retry logic inside the `execute_command` function-tool wrapper. The wrapper transparently re-runs the same command after a successful refresh, and the LLM sees only the second invocation's output.

**Alternatives considered:**
- *Intercept in the agent loop's tool-output handling.* The Agents SDK gives hooks for tool-end events, but mutating the result stream there is awkward and ties this to SDK internals.
- *Decorator on every tool that might hit gws.* Only `execute_command` invokes gws today; over-generalizing is premature.

**Rationale:** The tool function already owns the subprocess lifecycle — adding "after the subprocess, look at the output, optionally refresh + re-exec" is a local change with a tight blast radius. No SDK coupling.

### Decision 4: New HTTP endpoint, not a new MCP tool

**Choice:** Add `POST /api/google/refresh-token` on errand-server, authenticated with a per-task opaque bearer (stored in Valkey under `google_refresh_token:<bearer>` → `<task_id>`, TTL 8 h). The runner calls it via `httpx`.

**Alternatives considered:**
- *Expose as an MCP tool on the errand MCP server.* Two costs: (a) the runner would have to invoke an MCP tool from inside a function-tool body, which means the call appears in the conversation as a tool call (defeating "invisible to LLM"), or it means duplicating MCP client plumbing inside the wrapper. (b) MCP tools are LLM-callable by default, which we explicitly don't want for this one.
- *Reuse the global `mcp_api_key` setting as the bearer.* Initially shipped this way, but it's insecure: `mcp_api_key` is copied into `/workspace/mcp.json` for every task that runs the errand MCP server, so any task — including one whose profile excludes Google access — could read that file and call the endpoint to obtain the user's Google access token. Replaced with a per-task opaque bearer stored in Valkey (modelled on `RESULT_CALLBACK_TOKEN`), injected only when Google credentials are present, so the bearer's scope is bounded to "this task already had Google access".

**Rationale:** A plain HTTPS POST with a per-task bearer is the simplest secure surface. No SDK boundary, no LLM visibility, no new auth model, and the bearer's blast radius is one task.

### Decision 5: Force refresh, ignore the 5-min buffer

**Choice:** The endpoint SHALL invoke a forced refresh — not `refresh_token_if_needed` with its 300-second buffer. If the runner says the token is dead, the cached `expires_at` is by definition wrong.

**Implementation:** add a `force: bool` parameter (or a sibling helper `force_refresh_token`) in `errand/cloud_storage.py`. The new endpoint calls it with `force=True`. Internal task-start code keeps the buffer-based path.

**Rationale:** The runner has empirical proof of expiry. Re-applying the buffer check would short-circuit the refresh if `expires_at` in the DB is still "fresh" — exactly the case where a cached `expires_at` lies. Forcing eliminates the silent failure.

### Decision 6: Asyncio lock, single retry cap

**Choice:** A module-level `asyncio.Lock` guards the refresh call. Inside the lock, the wrapper re-reads `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]` first — if it differs from the value it saw at entry, another caller has already refreshed and we skip the network call. Retry is capped at 1 per `execute_command` invocation regardless.

**Alternatives considered:**
- *No lock, two parallel commands both refresh.* Tolerable but wasteful — two refresh round-trips and two `PlatformCredential` writes per genuine expiry event.
- *Multi-retry with backoff.* Adds complexity; if the first refresh-and-retry still returns `UNAUTHENTICATED`, something else is wrong (scopes revoked, account disabled) and looping won't help.

**Rationale:** Cheap insurance; matches the existing retry-once discipline in `task-runner-error-resilience`.

### Decision 7: Inject `ERRAND_API_URL` and `ERRAND_API_KEY` env vars

**Choice:** `task_manager.py` SHALL set `ERRAND_API_URL` (errand-server base URL, derived from `ERRAND_MCP_URL` by stripping the `/mcp/...` suffix) and `ERRAND_API_KEY` (= `mcp_api_key`) on every task-runner container. The wrapper reads these at refresh time.

**Alternatives considered:**
- *Parse `ERRAND_MCP_URL` at runtime in the runner.* Already done elsewhere on the server side (`cloud_storage._get_server_base_url`); plumbing a parsed base URL in is simpler than duplicating the parser in the runner.
- *Pull from the MCP config file.* The runner could read the Authorization header out of the parsed mcp.json. Works, but couples the wrapper to MCP-config format. A dedicated env var pair is clearer.

**Rationale:** Mirrors the existing `RESULT_CALLBACK_URL` / `RESULT_CALLBACK_TOKEN` pattern. Self-documenting; zero parsing in the runner.

## Risks / Trade-offs

- **Detection signature drift** → If a future version of `gws` (or the Google APIs it calls) changes the auth-error JSON shape, detection silently breaks. *Mitigation:* the signature is a Google API standard error field, not gws-specific. Add a unit test that pins the exact substring; log a one-shot warning if any `execute_command` returns nonzero with an auth-y-looking message we *didn't* match, so drift surfaces in observability.
- **False positives** → A user might run a command that legitimately emits the substring `"status": "UNAUTHENTICATED"` (e.g. `cat some_file.json`). *Mitigation:* accept the cost. Worst case: one extra refresh + one duplicate command execution. The refreshed token doesn't break anything; the re-exec produces the same output as the first. We could also additionally require `GOOGLE_WORKSPACE_CLI_TOKEN` to be set before triggering, which we do.
- **Refresh succeeds but the next gws call still 401s** → Could happen if the refresh token has been revoked yet still issues an access token, or if scopes changed. *Mitigation:* the one-retry cap returns the second failure to the LLM unchanged; the agent can choose to surface that to the user.
- **Non-idempotent commands** → If the wrapper re-runs a non-idempotent command (e.g. a `gws drive upload` that partially succeeded), retry could produce duplicate side effects. *Mitigation:* in practice an `UNAUTHENTICATED` response means the API call was rejected before any side effect was committed. Document this assumption; do not attempt to retry on any other error.
- **The runner cannot reach the errand API** (network policy, DNS) → Refresh fails, original error surfaces. *Mitigation:* clear log message; the same connectivity is already required for the errand MCP server, so this is a pre-existing failure mode, not a new one.
- **Concurrent tasks across pods refreshing simultaneously** → Two pods can each force-refresh and overwrite each other's `expires_at`. *Mitigation:* harmless — the second refresh just replaces the first with another valid token. No worker-side coordination needed.
- **Token leaks to logs** → The endpoint response includes the access token. *Mitigation:* don't log the response body; log only `task_id`, success/failure, and the new `expires_at`. The runner SHALL NOT log the new env var value.
- **Wrapper adds latency on every command** → Detection is a substring scan of (typically <50KB) stdout/stderr. Negligible. The slow path (refresh + retry) only fires on actual expiry.

## Migration Plan

- Ship as a normal release. No data migration. No flag — the wrapper activates on any task with `GOOGLE_WORKSPACE_CLI_TOKEN` injected.
- Older runner images will continue to fail tasks as today until rolled forward — no compatibility break.
- The new errand endpoint is additive; older runners simply never call it.
- Rollback: revert the runner image. The endpoint can be left in place (no callers).

## Open Questions

- Should we emit a runner event (`token_refreshed`) into the task transcript so a user reading the transcript can see the refresh happened? *Tentative answer: yes — adds zero LLM context but useful for ops debugging.*
- Should the errand endpoint also accept refreshes for `onedrive` (returning the new token), to prepare for the future OneDrive change? *Tentative answer: scope to google for this change; revisit when OneDrive lands.*
