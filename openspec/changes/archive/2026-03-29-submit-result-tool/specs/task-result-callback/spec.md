## MODIFIED Requirements

### Requirement: Internal result callback endpoint

The backend SHALL expose `POST /api/internal/task-result/{task_id}` as an internal endpoint for the task-runner to push its structured output. The endpoint SHALL NOT use OIDC authentication. Instead, the endpoint SHALL read a `Bearer` token from the `Authorization` header and validate it against the expected token stored in Valkey at key `task_result_token:{task_id}` using constant-time comparison (`secrets.compare_digest`). If the token is missing, not found in Valkey, or does not match, the endpoint SHALL return HTTP 401. On successful validation, the endpoint SHALL: (1) delete the token key from Valkey (one-time use), (2) store the raw request body at Valkey key `task_result:{task_id}` with a TTL of 10 minutes, (3) return HTTP 200 with `{"ok": true}`.

The callback payload SHALL be a JSON object with `status` (string), `result` (string), and optionally `questions` (array of strings) and `error` (string). The task-runner SHALL construct this payload from validated, structured fields (either from a `submit_result` tool call or from parsed text output), not by re-serializing an intermediate model object. This ensures the `result` field contains clean content without JSON wrapper artifacts.

#### Scenario: Valid token and result stored

- **WHEN** the task-runner POSTs a JSON body to `/api/internal/task-result/{task_id}` with a valid `Authorization: Bearer <token>` matching the Valkey-stored token
- **THEN** the endpoint stores the body at `task_result:{task_id}` with 10-minute TTL, deletes the token, and returns 200

#### Scenario: Invalid token rejected

- **WHEN** a request is made to `/api/internal/task-result/{task_id}` with a `Bearer` token that does not match the Valkey-stored token
- **THEN** the endpoint returns HTTP 401 and does not store any result

#### Scenario: Missing token rejected

- **WHEN** a request is made to `/api/internal/task-result/{task_id}` without an `Authorization` header
- **THEN** the endpoint returns HTTP 401

#### Scenario: Expired or absent token key

- **WHEN** a request is made to `/api/internal/task-result/{task_id}` but no token exists in Valkey for that task_id (expired or never created)
- **THEN** the endpoint returns HTTP 401

#### Scenario: Token consumed after single use

- **WHEN** the task-runner successfully POSTs a result and receives 200
- **THEN** a second POST with the same token returns HTTP 401 because the token was deleted after first use

#### Scenario: Valkey unavailable

- **WHEN** the Valkey connection is not available when the endpoint is called
- **THEN** the endpoint returns HTTP 503

#### Scenario: Callback payload from submit_result tool

- **WHEN** the task-runner posts a result originating from a `submit_result` tool call
- **THEN** the payload contains `{"status": "completed", "result": "...", "questions": []}` where `result` is the clean markdown content from the tool arguments, not a re-serialized JSON wrapper

#### Scenario: Callback payload from text fallback

- **WHEN** the task-runner posts a result extracted from text-based JSON output (backward compatibility)
- **THEN** the payload contains the same structure with `result` extracted from the parsed JSON, not the raw JSON string
