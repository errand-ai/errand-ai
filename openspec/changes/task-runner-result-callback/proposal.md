## Why

The worker currently pulls task-runner output after the container exits — via Docker `container.logs()` or K8s `exec` into the pod. The K8s exec approach always fails for batch Jobs because the container is terminated before exec runs, producing noisy `container not found` warnings. A log-scanning fallback works but is fragile and unreliable. Switching to a push-based model gives consistent output handling regardless of deployment type.

## What Changes

- Add a new internal API endpoint (`POST /api/internal/task-result/{task_id}`) that accepts task-runner output JSON, secured with a one-time Valkey token
- Task-runner POSTs its structured output to the callback URL before exiting
- Worker generates a one-time callback token (stored in Valkey), passes `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` as env vars to the task-runner container
- Worker reads the pushed result from Valkey after container exits, falling back to the existing `runtime.result()` if the callback didn't arrive
- Existing Docker/K8s result retrieval paths remain as fallbacks (no removal)

## Capabilities

### New Capabilities
- `task-result-callback`: Internal API endpoint for task-runner to push structured output, with one-time token auth and Valkey-based result storage

### Modified Capabilities
- `task-runner-agent`: Task-runner gains a `post_result_callback()` function that POSTs output to the backend before exiting
- `task-worker`: Worker generates callback tokens, passes callback env vars to containers, and reads pushed results from Valkey

## Impact

- **Backend API** (`backend/main.py`): New unprotected endpoint with Valkey token auth
- **Worker** (`backend/worker.py`): Token generation, env var injection, Valkey result reading
- **Task-runner** (`task-runner/main.py`): New HTTP POST call before exit
- **Valkey**: Two new key patterns (`task_result_token:{id}`, `task_result:{id}`) with TTLs
- **No Helm changes**: Callback URL derived from existing `BACKEND_MCP_URL` at runtime
- **No breaking changes**: Existing result retrieval paths remain as fallbacks
