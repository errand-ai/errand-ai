## MODIFIED Requirements

### Requirement: Worker executes tasks via ContainerRuntime

The worker SHALL generate a one-time callback token using `secrets.token_hex(32)` and store it in Valkey at key `task_result_token:{task_id}` with a TTL of 30 minutes. The worker SHALL derive the callback URL by stripping the `/mcp` suffix from the existing `ERRAND_MCP_URL` environment variable and appending `/api/internal/task-result/{task_id}`. The worker SHALL pass `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` as environment variables to the task-runner container alongside the existing env vars. If Valkey is unavailable when storing the token, the worker SHALL log a warning and omit both callback env vars (graceful degradation — the task-runner will skip the callback POST).

All other behaviour (settings retrieval, system prompt construction, MCP configuration injection, Perplexity injection, Hindsight recall, skills injection, SSH credential injection, env var substitution, log publishing to Valkey, output parsing, retry logic, repeating task rescheduling, WebSocket event publishing) SHALL remain unchanged.

#### Scenario: Callback URL derived from ERRAND_MCP_URL
- **WHEN** `ERRAND_MCP_URL` is `http://errand:8000/mcp` and the task ID is `abc-123`
- **THEN** `RESULT_CALLBACK_URL` is `http://errand:8000/api/internal/task-result/abc-123`
