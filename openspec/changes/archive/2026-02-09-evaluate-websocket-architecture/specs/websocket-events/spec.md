## ADDED Requirements

### Requirement: WebSocket endpoint for task events
The backend SHALL expose a WebSocket endpoint at `WS /api/ws/tasks` that pushes task change events to connected clients in real time.

#### Scenario: Client connects successfully
- **WHEN** a client opens a WebSocket connection to `/api/ws/tasks?token=<valid-jwt>`
- **THEN** the backend accepts the connection and begins delivering task events

#### Scenario: Client receives task created event
- **WHEN** a task is created via `POST /api/tasks`
- **THEN** all connected WebSocket clients receive a JSON message with `{"event": "task_created", "task": {...}}` containing the full task object

#### Scenario: Client receives task updated event
- **WHEN** a task is updated via `PATCH /api/tasks/{id}`
- **THEN** all connected WebSocket clients receive a JSON message with `{"event": "task_updated", "task": {...}}` containing the full updated task object

#### Scenario: Client receives worker-driven status change
- **WHEN** the worker transitions a task from `pending` to `running` or from `running` to `completed`
- **THEN** all connected WebSocket clients receive a `task_updated` event with the new task state

### Requirement: WebSocket authentication via query parameter
The WebSocket endpoint SHALL authenticate clients using a JWT token passed as a `token` query parameter. Connections without a valid token SHALL be rejected.

#### Scenario: Valid token accepted
- **WHEN** a client connects to `/api/ws/tasks?token=<valid-jwt>`
- **THEN** the backend validates the token and accepts the connection

#### Scenario: Missing token rejected
- **WHEN** a client connects to `/api/ws/tasks` without a `token` parameter
- **THEN** the backend closes the connection with WebSocket close code 4001

#### Scenario: Invalid token rejected
- **WHEN** a client connects to `/api/ws/tasks?token=<invalid-jwt>`
- **THEN** the backend closes the connection with WebSocket close code 4001

#### Scenario: Expired token rejected
- **WHEN** a client connects to `/api/ws/tasks?token=<expired-jwt>`
- **THEN** the backend closes the connection with WebSocket close code 4001

### Requirement: Event message format
All WebSocket messages SHALL be JSON objects with an `event` field and a `task` field. The `task` field SHALL match the `TaskResponse` schema (`id`, `title`, `status`, `created_at`, `updated_at`).

#### Scenario: Message structure
- **WHEN** a task event is published
- **THEN** the WebSocket message is a JSON object: `{"event": "<event_type>", "task": {"id": "...", "title": "...", "status": "...", "created_at": "...", "updated_at": "..."}}`

#### Scenario: Event types
- **WHEN** events are published
- **THEN** the `event` field SHALL be one of: `task_created`, `task_updated`

### Requirement: Valkey pub/sub for cross-replica broadcasting
The backend SHALL use Valkey pub/sub to broadcast task events across all backend replicas. Each backend replica SHALL subscribe to the Valkey channel and forward received events to its locally connected WebSocket clients.

#### Scenario: Multi-replica event delivery
- **WHEN** a task is created on backend replica A
- **THEN** WebSocket clients connected to both replica A and replica B receive the event

#### Scenario: Valkey connection configured via environment
- **WHEN** the backend starts
- **THEN** it reads the Valkey connection URL from the `VALKEY_URL` environment variable (default: `redis://localhost:6379`)

### Requirement: Valkey publish failure is non-blocking
Publishing events to Valkey SHALL NOT block or fail the REST API response. If Valkey is unavailable, the API endpoint SHALL still return successfully and log a warning.

#### Scenario: Valkey unavailable during task creation
- **WHEN** a client sends `POST /api/tasks` and Valkey is down
- **THEN** the task is created successfully (HTTP 201) and a warning is logged

#### Scenario: Valkey unavailable during task update
- **WHEN** a client sends `PATCH /api/tasks/{id}` and Valkey is down
- **THEN** the task is updated successfully (HTTP 200) and a warning is logged

### Requirement: WebSocket keepalive
The backend SHALL send periodic ping frames to connected WebSocket clients to keep connections alive through proxies and load balancers.

#### Scenario: Idle connection stays open
- **WHEN** a WebSocket client is connected but no task events occur for 30 seconds
- **THEN** the backend sends a ping frame and the connection remains open

#### Scenario: Unresponsive client disconnected
- **WHEN** a WebSocket client does not respond to a ping frame within 10 seconds
- **THEN** the backend closes the connection

### Requirement: Worker publishes events to Valkey
The worker process SHALL publish `task_updated` events to the Valkey pub/sub channel after each task status transition.

#### Scenario: Worker transitions task to running
- **WHEN** the worker changes a task status from `pending` to `running`
- **THEN** the worker publishes a `task_updated` event to Valkey with the updated task state

#### Scenario: Worker transitions task to completed
- **WHEN** the worker changes a task status from `running` to `completed`
- **THEN** the worker publishes a `task_updated` event to Valkey with the updated task state

#### Scenario: Worker Valkey failure is non-blocking
- **WHEN** the worker completes a task but Valkey is unavailable
- **THEN** the task status is still updated in the database and a warning is logged
