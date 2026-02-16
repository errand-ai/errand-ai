## Requirements

### Requirement: Per-task Valkey pub/sub channel for log streaming

The worker SHALL publish structured task runner events to a per-task Valkey pub/sub channel named `task_logs:{task_id}` during container execution. Each stderr line from the task runner container SHALL be parsed as JSON. If the line is valid JSON with `type` and `data` fields, it SHALL be published as `{"event": "task_event", "type": "<event_type>", "data": <event_data>}`. If the line is not valid JSON, it SHALL be published as `{"event": "task_event", "type": "raw", "data": {"line": "<raw_line>"}}`. When container execution completes (regardless of exit code), the worker SHALL publish a final message `{"event": "task_log_end"}` on the same channel.

#### Scenario: Structured event published during execution

- **WHEN** the worker executes a task with id `abc-123` and the container emits stderr line `{"type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}`
- **THEN** the worker publishes `{"event": "task_event", "type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}` to the Valkey channel `task_logs:abc-123`

#### Scenario: Non-JSON stderr line published as raw event

- **WHEN** the worker reads a stderr line `Traceback (most recent call last):` that is not valid JSON
- **THEN** the worker publishes `{"event": "task_event", "type": "raw", "data": {"line": "Traceback (most recent call last):"}}` to the Valkey channel

#### Scenario: End sentinel published after container exit

- **WHEN** the worker finishes streaming stderr for task `abc-123` (container has exited)
- **THEN** the worker publishes `{"event": "task_log_end"}` to the Valkey channel `task_logs:abc-123`

#### Scenario: End sentinel published on non-zero exit

- **WHEN** the worker executes a task and the container exits with a non-zero exit code
- **THEN** the worker publishes `{"event": "task_log_end"}` to the channel after all stderr lines have been published

#### Scenario: No subscribers has no effect

- **WHEN** the worker publishes events to `task_logs:{task_id}` and no clients are subscribed
- **THEN** the messages are silently discarded by Valkey and the worker is not affected

#### Scenario: Valkey unavailable during event publishing

- **WHEN** the worker attempts to publish an event and the sync Redis connection fails
- **THEN** the worker logs a warning and continues execution without interrupting task processing

### Requirement: WebSocket endpoint for live task logs

The backend SHALL expose a WebSocket endpoint at `WS /api/ws/tasks/{task_id}/logs` that streams live stderr log lines from a running task to connected clients. The endpoint SHALL authenticate using a JWT token passed as a `token` query parameter, following the same auth pattern as the existing `/api/ws/tasks` endpoint.

#### Scenario: Client connects and receives live logs
- **WHEN** a client opens a WebSocket connection to `/api/ws/tasks/{task_id}/logs?token=<valid-jwt>` while the task is in `running` status
- **THEN** the backend subscribes to the `task_logs:{task_id}` Valkey channel and forwards each message as a WebSocket text frame

#### Scenario: Client receives end sentinel
- **WHEN** the connected client receives a message with `{"event": "task_log_end"}`
- **THEN** the backend sends the message to the client and closes the WebSocket connection with a normal close code (1000)

#### Scenario: Client connects to non-running task
- **WHEN** a client opens a WebSocket connection to `/api/ws/tasks/{task_id}/logs` and the task status is not `running`
- **THEN** the backend sends `{"event": "task_log_end"}` and closes the connection with close code 1000

#### Scenario: Missing token rejected
- **WHEN** a client connects to `/api/ws/tasks/{task_id}/logs` without a `token` parameter
- **THEN** the backend closes the connection with WebSocket close code 4001

#### Scenario: Invalid token rejected
- **WHEN** a client connects with an invalid or expired JWT token
- **THEN** the backend closes the connection with WebSocket close code 4001

#### Scenario: Multiple clients view same task logs
- **WHEN** two clients connect to `/api/ws/tasks/{task_id}/logs` for the same running task
- **THEN** both clients receive the same log lines independently via their own Valkey subscriptions

#### Scenario: Client disconnects during streaming
- **WHEN** a client closes the WebSocket connection while logs are still streaming
- **THEN** the backend unsubscribes from the Valkey channel and cleans up resources

### Requirement: Live log viewer button on running task cards

The frontend SHALL display a "View Logs" button on task cards when the task is in the `running` status. The button SHALL emit a `view-logs` event when clicked.

#### Scenario: Button visible on running task
- **WHEN** a task card is rendered with status `running`
- **THEN** a "View Logs" button is visible on the card

#### Scenario: Button hidden on non-running tasks
- **WHEN** a task card is rendered with status `new`, `pending`, `scheduled`, `review`, or `completed`
- **THEN** the "View Logs" button is not visible

#### Scenario: Button click emits event
- **WHEN** the user clicks the "View Logs" button on a running task card
- **THEN** the card emits a `view-logs` event with no payload

### Requirement: Live log viewer modal

The frontend SHALL provide a `TaskLogModal` component that displays live stderr output from a running task. The modal SHALL open a WebSocket connection to `/api/ws/tasks/{task_id}/logs` when mounted and close it when unmounted.

#### Scenario: Modal displays streaming log lines
- **WHEN** the log viewer modal is opened for a running task and the WebSocket receives `{"event": "task_log", "line": "INFO Starting agent"}`
- **THEN** the modal appends `"INFO Starting agent"` to the displayed log output

#### Scenario: Auto-scroll follows new output
- **WHEN** the log viewer is open and new log lines arrive
- **THEN** the log display auto-scrolls to show the latest line

#### Scenario: Stream ends gracefully
- **WHEN** the WebSocket receives `{"event": "task_log_end"}`
- **THEN** the modal displays a "Task finished" indicator and stops waiting for new lines

#### Scenario: Modal close disconnects WebSocket
- **WHEN** the user closes the log viewer modal (via Close button, Escape, or backdrop click)
- **THEN** the WebSocket connection is closed

#### Scenario: Empty log state
- **WHEN** the log viewer modal opens and no log lines have been received yet
- **THEN** the modal displays a waiting indicator (e.g., "Waiting for logs...")

#### Scenario: Modal uses terminal-style presentation
- **WHEN** the log viewer modal is displaying log lines
- **THEN** the output area uses a monospace font with dark background and light text, presented in a scrollable container
