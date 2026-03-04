## ADDED Requirements

### Requirement: SSE endpoint for task board events

The backend SHALL expose an SSE endpoint at `GET /api/events?token={jwt}` that streams real-time task events to connected frontend clients. This replaces the WebSocket endpoint `WS /api/ws/tasks`.

The endpoint SHALL:
- Validate the JWT token from the `token` query parameter
- Subscribe to the `task_events` Valkey pub/sub channel
- Forward each event as an SSE message with `event:` set to the event type and `data:` set to the JSON payload
- Keep the connection open indefinitely until the client disconnects
- Set response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`

Event types:
- `task_created` — data contains full TaskData
- `task_updated` — data contains full TaskData
- `task_deleted` — data contains `{ id: string }`
- `cloud_status` — data contains `{ status: string, detail?: string }`

#### Scenario: Client connects and receives task update

- **WHEN** a client opens an SSE connection to `/api/events?token=<valid-jwt>`
- **AND** a task is updated in the system
- **THEN** the client receives an SSE message: `event: task_updated\ndata: {"id": "42", "status": "completed", ...}\n\n`

#### Scenario: Multiple event types

- **WHEN** a client is connected to the SSE endpoint
- **AND** a new task is created, then another task is deleted
- **THEN** the client receives a `task_created` event followed by a `task_deleted` event, in order

#### Scenario: Client disconnect cleanup

- **WHEN** a client closes its SSE connection
- **THEN** the backend unsubscribes from the Valkey channel for that client
- **AND** no further events are sent

### Requirement: SSE task events authentication

The SSE endpoint SHALL authenticate clients using a JWT token passed as a `token` query parameter, using the same validation logic as existing authenticated endpoints (supporting local, SSO, and cloud-trusted auth modes).

#### Scenario: Valid token accepted

- **WHEN** a client connects to `/api/events?token=<valid-jwt>`
- **THEN** the connection is accepted and events begin streaming

#### Scenario: Missing token rejected

- **WHEN** a client connects to `/api/events` without a `token` parameter
- **THEN** the server responds with HTTP 401

#### Scenario: Invalid token rejected

- **WHEN** a client connects with an invalid JWT token
- **THEN** the server responds with HTTP 401

#### Scenario: Expired token rejected

- **WHEN** a client connects with an expired JWT token
- **THEN** the server responds with HTTP 401
