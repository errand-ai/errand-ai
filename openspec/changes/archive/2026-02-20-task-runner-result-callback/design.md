## Context

The worker retrieves task-runner output using a pull model: Docker reads `container.logs()`, K8s attempts `exec` into the pod then falls back to log scanning. The K8s exec always fails for completed Jobs (`container not found`), and log scanning is fragile (parsing JSON from merged stdout/stderr). Both the backend and worker already use Valkey for event pub/sub and log streaming.

## Goals / Non-Goals

**Goals:**
- Consistent result delivery regardless of container runtime (Docker or K8s)
- Task-runner pushes output to backend before exiting
- Secure callback endpoint (not exploitable by external users)
- Graceful degradation when callback fails

**Non-Goals:**
- Removing existing Docker/K8s result retrieval paths (they become fallbacks)
- Streaming incremental results (this is final output only)
- Replacing the existing log streaming mechanism (Valkey pubsub for live logs is unchanged)

## Decisions

### 1. Push via HTTP callback to backend API

**Decision:** Task-runner POSTs result JSON to `POST /api/internal/task-result/{task_id}` on the backend.

**Alternatives considered:**
- *Task-runner writes directly to Valkey* — requires adding Redis client to task-runner dependencies and passing `VALKEY_URL`. The task-runner shouldn't need to know about internal infrastructure.
- *Task-runner writes to shared volume* — already tried via `/output/result.json` on emptyDir, but reading it back requires exec which fails for completed pods.

**Rationale:** The backend already serves HTTP and has Valkey access. The task-runner already makes HTTP calls (OpenAI, MCP servers). An HTTP POST is the simplest integration that keeps the task-runner decoupled from infrastructure details.

### 2. One-time Valkey token for auth

**Decision:** Worker generates `secrets.token_hex(32)`, stores it in Valkey at `task_result_token:{task_id}` (TTL 30 min), passes it to the task-runner as `RESULT_CALLBACK_TOKEN` env var. The backend endpoint validates with `secrets.compare_digest` and deletes the token after use.

**Alternatives considered:**
- *No auth (internal-only)* — the endpoint is reachable via ingress, so external users could submit fake results.
- *OIDC/JWT* — task-runner has no user credentials, and issuing service tokens adds complexity.
- *Static shared secret* — less secure than per-task tokens, and harder to audit.

**Rationale:** One-time tokens are simple, secure, and self-cleaning. No new dependencies. The worker already has `sync_redis` and `secrets` available.

**Token refresh:** The worker's log-streaming loop (`runtime.run()`) iterates on each log line from the container. During this loop the worker periodically refreshes the token TTL (every 15 minutes) so that long-running tasks don't lose their callback token. The refresh uses `EXPIRE` (reset TTL) on the existing key — the token value doesn't change, so the task-runner's env var stays valid.

**Token cleanup:** The token is deleted in three places to ensure no stale tokens remain:
1. The backend endpoint deletes the token immediately after successful validation (one-time use).
2. The worker explicitly deletes `task_result_token:{task_id}` after reading the callback result from Valkey (regardless of whether the callback arrived).
3. The TTL acts as a final safety net if both the above paths fail (e.g., worker crash).

### 3. Valkey as intermediate result store

**Decision:** Backend endpoint stores the POSTed result in Valkey at `task_result:{task_id}` (TTL 10 min). Worker reads it after `runtime.result()` returns.

**Alternatives considered:**
- *Store directly in Task DB row* — race condition with worker's own Task update. Mixing concerns between API and worker.
- *Return result synchronously to worker via callback* — worker isn't listening for HTTP responses.

**Rationale:** Valkey is already the shared bus between backend and worker. Ephemeral storage with TTL is perfect for a handoff that happens within seconds.

### 4. Callback URL derived from BACKEND_MCP_URL

**Decision:** Worker derives the callback URL by stripping `/mcp` from the existing `BACKEND_MCP_URL` env var and appending `/api/internal/task-result/{task_id}`.

**Rationale:** Avoids adding another Helm env var. `BACKEND_MCP_URL` is already set as `http://errand-backend:8000/mcp` by the Helm chart. In Docker mode with `network_mode=host`, the task-runner container shares the network namespace, so the same hostname resolves correctly.

### 5. Worker reads Valkey after runtime.result()

**Decision:** Worker calls `runtime.result(handle)` as before (to get exit code and stderr), then checks Valkey for the callback result. If found, overrides stdout with the Valkey value.

**Rationale:** Minimal change to the existing flow. `runtime.result()` still provides exit code and stderr (logs). The callback result only replaces stdout (the structured JSON output). No changes to the ContainerRuntime ABC.

## Risks / Trade-offs

- **[Network failure between task-runner and backend]** → Existing fallback paths (Docker container.logs, K8s log scanning) remain intact. Task-runner logs a warning but still exits normally.
- **[Token expires before task-runner finishes]** → Worker refreshes the token TTL every 15 minutes during log streaming. As long as the worker is alive and streaming logs, the token stays valid.
- **[Valkey unavailable]** → Token storage fails silently in worker (callback env vars not set), task-runner skips POST (env vars absent), worker falls back to runtime.result(). Full graceful degradation.
- **[Callback endpoint exposed via ingress]** → One-time token prevents exploitation. Token is 256-bit random hex, deleted after use.
