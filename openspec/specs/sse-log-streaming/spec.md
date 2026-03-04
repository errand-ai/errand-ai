## ADDED Requirements

### Requirement: SSE endpoint for live task log streaming

The backend SHALL expose an SSE endpoint at `GET /api/tasks/{task_id}/logs/stream?token={jwt}` that streams live task runner log lines to connected frontend clients. This replaces the WebSocket endpoint `WS /api/ws/tasks/{task_id}/logs`.

The endpoint SHALL:
- Validate the JWT token from the `token` query parameter
- Verify the task exists and is in `running` status
- Subscribe to the `task_logs:{task_id}` Valkey pub/sub channel
- Forward each log line as an SSE message with `event: log` and `data:` set to the log line content
- Send `event: task_log_end` when the task finishes
- Close the connection after sending `task_log_end`

#### Scenario: Client connects and receives live logs

- **WHEN** a client opens an SSE connection to `/api/tasks/42/logs/stream?token=<valid-jwt>` while task 42 is in `running` status
- **THEN** the backend subscribes to the `task_logs:42` Valkey channel and forwards each message as an SSE event

#### Scenario: Task finishes during streaming

- **WHEN** the backend receives `{"event": "task_log_end"}` from the Valkey channel
- **THEN** the backend sends `event: task_log_end\ndata: {}\n\n` and closes the SSE connection

#### Scenario: Client connects to non-running task

- **WHEN** a client connects and the task's current status is not `running`
- **THEN** the backend sends `event: task_log_end\ndata: {}\n\n` and closes the connection

#### Scenario: Client connects to non-existent task

- **WHEN** a client connects with a task_id that does not exist
- **THEN** the server responds with HTTP 404

### Requirement: SSE log streaming authentication

The SSE log streaming endpoint SHALL authenticate clients using a JWT token passed as a `token` query parameter, using the same validation logic as existing authenticated endpoints.

#### Scenario: Valid token accepted

- **WHEN** a client connects to `/api/tasks/{task_id}/logs/stream?token=<valid-jwt>`
- **THEN** the connection is accepted and log lines begin streaming

#### Scenario: Missing token rejected

- **WHEN** a client connects without a `token` parameter
- **THEN** the server responds with HTTP 401

#### Scenario: Invalid token rejected

- **WHEN** a client connects with an invalid JWT token
- **THEN** the server responds with HTTP 401
