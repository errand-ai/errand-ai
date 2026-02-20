## 1. Backend Endpoint

- [x] 1.1 Add `POST /api/internal/task-result/{task_id}` endpoint to `backend/main.py` — read `Authorization: Bearer` header, validate token against Valkey key `task_result_token:{task_id}` using `secrets.compare_digest`, delete token on match, store request body at `task_result:{task_id}` with 10-min TTL, return `{"ok": true}`. Return 401 for missing/invalid/expired tokens. Return 503 if Valkey is unavailable.
- [x] 1.2 Add backend tests for the callback endpoint: valid token stores result and returns 200, invalid token returns 401, missing Authorization header returns 401, expired/absent token returns 401, token consumed after single use (second POST returns 401), Valkey unavailable returns 503.

## 2. Worker Token Generation and Env Vars

- [x] 2.1 In `process_task_in_container()`, after env_vars construction (~line 670) and before `runtime.prepare()`: generate `secrets.token_hex(32)`, store in Valkey at `task_result_token:{task_id}` with 30-min TTL using sync Redis, derive callback URL from `BACKEND_MCP_URL` (strip `/mcp`, append `/api/internal/task-result/{task_id}`), add `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` to env_vars. If Valkey write fails, log warning and skip both env vars.
- [x] 2.2 Add token TTL refresh in the log-streaming loop: track elapsed time, call `EXPIRE task_result_token:{task_id} 1800` every 15 minutes during `runtime.run()` iteration.
- [x] 2.3 Add worker tests for token generation: token stored in Valkey with correct key and TTL, callback URL correctly derived from BACKEND_MCP_URL, both env vars passed to container, Valkey failure gracefully skips callback env vars.

## 3. Worker Reads Callback Result

- [x] 3.1 Add `_read_callback_result(task_id: str)` helper using sync Redis: read and delete `task_result:{task_id}`, also delete `task_result_token:{task_id}` for cleanup. Return `str | None`, swallow all exceptions.
- [x] 3.2 After `runtime.result()` returns (~line 843), call `_read_callback_result()`. If result found, override stdout with callback result before `truncate_output()`.
- [x] 3.3 Add worker tests for callback result reading: callback result overrides runtime stdout, missing callback falls back to runtime stdout, both Valkey keys deleted after reading, Valkey errors swallowed gracefully.

## 4. Task-Runner Callback POST

- [x] 4.1 Add `post_result_callback(output: str)` function to `task-runner/main.py`: read `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` from env, return silently if either missing, POST output with `Content-Type: application/json` and `Authorization: Bearer` headers using `httpx` with 10-second timeout, log success or warning on failure, never raise.
- [x] 4.2 Call `post_result_callback(output)` between `print(output)` and `write_output_file(output)` (~line 453).
- [x] 4.3 Add task-runner tests for callback POST: successful POST logs success, failed POST logs warning and doesn't raise, missing env vars cause silent no-op, timeout handled gracefully.
