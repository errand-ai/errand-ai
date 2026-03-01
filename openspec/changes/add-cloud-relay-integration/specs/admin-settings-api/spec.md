## MODIFIED Requirements

### Requirement: Cloud status event type
The existing task events WebSocket channel SHALL support a new `cloud_status` event type for real-time cloud connection state updates.

#### Scenario: Cloud status event published
- **WHEN** the cloud WebSocket client connects, disconnects, or encounters an error
- **THEN** a `cloud_status` event SHALL be published to the `task_events` Valkey channel
- **THEN** the event SHALL have the format: `{"event": "cloud_status", "status": "<connected|disconnected|error>", "detail": "<optional>"}`
- **THEN** all connected frontend WebSocket clients SHALL receive the event
