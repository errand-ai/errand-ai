## Purpose

WebSocket endpoint for per-task live log streaming from Valkey pub/sub to connected frontend clients.

## Requirements

### Requirement: WebSocket endpoint for per-task log streaming

The backend SHALL expose a WebSocket endpoint at `WS /api/ws/tasks/{task_id}/logs` that streams live task runner stderr log lines to connected clients. This endpoint is separate from the existing `/api/ws/tasks` task-events endpoint.

#### Scenario: Client connects and receives live logs
- **WHEN** a client opens a WebSocket connection to `/api/ws/tasks/{task_id}/logs?token=<valid-jwt>` while the task is in `running` status
- **THEN** the backend subscribes to the `task_logs:{task_id}` Valkey channel and forwards each message as a WebSocket text frame

#### Scenario: Client receives end sentinel and connection closes
- **WHEN** the backend receives `{"event": "task_log_end"}` from the Valkey channel
- **THEN** the backend forwards the message to the client and closes the WebSocket connection with close code 1000

#### Scenario: Client connects to non-running task
- **WHEN** a client opens a WebSocket connection and the task's current status is not `running`
- **THEN** the backend sends `{"event": "task_log_end"}` and closes the connection with close code 1000

#### Scenario: Client connects to non-existent task
- **WHEN** a client opens a WebSocket connection with a task_id that does not exist in the database
- **THEN** the backend closes the connection with WebSocket close code 4004

### Requirement: Log streaming WebSocket authentication

The log streaming WebSocket endpoint SHALL authenticate clients using a JWT token passed as a `token` query parameter, following the same validation logic as the existing `/api/ws/tasks` endpoint.

#### Scenario: Valid token accepted
- **WHEN** a client connects to `/api/ws/tasks/{task_id}/logs?token=<valid-jwt>`
- **THEN** the backend validates the token and accepts the connection

#### Scenario: Missing token rejected
- **WHEN** a client connects without a `token` parameter
- **THEN** the backend closes the connection with WebSocket close code 4001

#### Scenario: Invalid token rejected
- **WHEN** a client connects with an invalid JWT token
- **THEN** the backend closes the connection with WebSocket close code 4001

#### Scenario: Expired token rejected
- **WHEN** a client connects with an expired JWT token
- **THEN** the backend closes the connection with WebSocket close code 4001
