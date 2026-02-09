## MODIFIED Requirements

### Requirement: Board reflects live task state
The frontend SHALL connect to the backend WebSocket endpoint (`/api/ws/tasks`) to receive real-time task events. When a WebSocket event is received, the frontend SHALL update its local task store immediately without a full reload. The frontend SHALL fall back to polling `GET /api/tasks` at a regular interval if the WebSocket connection is unavailable.

#### Scenario: Task moves columns via WebSocket event
- **WHEN** a `task_updated` event is received with a new status
- **THEN** the task card moves to the appropriate column immediately without waiting for a poll cycle

#### Scenario: New task appears via WebSocket event
- **WHEN** a `task_created` event is received
- **THEN** the new task card appears in the New column immediately

#### Scenario: WebSocket connection established on load
- **WHEN** the user navigates to the application root and is authenticated
- **THEN** the frontend opens a WebSocket connection to `/api/ws/tasks` with the JWT token

#### Scenario: Fallback to polling on WebSocket failure
- **WHEN** the WebSocket connection cannot be established or is lost
- **THEN** the frontend falls back to polling `GET /api/tasks` every 5 seconds

#### Scenario: WebSocket reconnection with backoff
- **WHEN** the WebSocket connection is lost
- **THEN** the frontend attempts to reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)

#### Scenario: Polling stops when WebSocket reconnects
- **WHEN** the WebSocket connection is re-established after a fallback to polling
- **THEN** the frontend stops polling and resumes receiving events via WebSocket

#### Scenario: Task movement is animated
- **WHEN** a task card moves between columns after a WebSocket event
- **THEN** the card animates out of the source column and into the destination column using Vue's TransitionGroup
