## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

The worker SHALL generate a one-time callback token using `secrets.token_hex(32)` and store it in Valkey at key `task_result_token:{task_id}` with a TTL of 30 minutes. The worker SHALL derive the callback URL by stripping the `/mcp` suffix from the existing `BACKEND_MCP_URL` environment variable and appending `/api/internal/task-result/{task_id}`. The worker SHALL pass `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` as environment variables to the task-runner container alongside the existing env vars. If Valkey is unavailable when storing the token, the worker SHALL log a warning and omit both callback env vars (graceful degradation — the task-runner will skip the callback POST).

During the log-streaming loop, the worker SHALL refresh the token TTL by calling `EXPIRE` on the `task_result_token:{task_id}` key every 15 minutes, resetting the TTL to 30 minutes. This ensures long-running tasks retain a valid callback token for the duration of execution.

After `runtime.result()` returns, the worker SHALL check Valkey for a callback result at key `task_result:{task_id}`. If found, the worker SHALL use the callback result as stdout (overriding the value from `runtime.result()`). The worker SHALL then delete both `task_result:{task_id}` and `task_result_token:{task_id}` from Valkey to clean up. If the callback result is not found in Valkey, the worker SHALL proceed with the stdout from `runtime.result()` as before (existing fallback). All Valkey operations in this flow SHALL use the synchronous Redis client and SHALL swallow exceptions to avoid interrupting task processing.

#### Scenario: Callback token generated and passed to container

- **WHEN** the worker prepares a task-runner container and Valkey is available
- **THEN** the worker generates a 64-character hex token, stores it at `task_result_token:{task_id}` with 30-min TTL, and passes `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` to the container

#### Scenario: Callback URL derived from BACKEND_MCP_URL

- **WHEN** `BACKEND_MCP_URL` is `http://errand-backend:8000/mcp` and the task ID is `abc-123`
- **THEN** `RESULT_CALLBACK_URL` is `http://errand-backend:8000/api/internal/task-result/abc-123`

#### Scenario: Token TTL refreshed during long-running tasks

- **WHEN** a task runs for more than 15 minutes and the worker is streaming logs
- **THEN** the worker calls `EXPIRE task_result_token:{task_id} 1800` every 15 minutes to keep the token valid

#### Scenario: Callback result overrides runtime stdout

- **WHEN** the task-runner POSTs its result to the callback and the worker reads it from Valkey after `runtime.result()`
- **THEN** the worker uses the Valkey callback result as stdout instead of the value from `runtime.result()`

#### Scenario: Fallback to runtime stdout when callback absent

- **WHEN** the task-runner does not POST a callback result (env vars absent, network failure, or timeout)
- **THEN** the worker uses stdout from `runtime.result()` as before

#### Scenario: Token and result cleaned up after reading

- **WHEN** the worker reads (or attempts to read) the callback result from Valkey
- **THEN** the worker deletes both `task_result:{task_id}` and `task_result_token:{task_id}` regardless of whether the callback arrived

#### Scenario: Valkey unavailable during token storage

- **WHEN** Valkey is not reachable when the worker tries to store the callback token
- **THEN** the worker logs a warning, omits `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` from container env vars, and proceeds with task execution (task-runner will skip callback)
