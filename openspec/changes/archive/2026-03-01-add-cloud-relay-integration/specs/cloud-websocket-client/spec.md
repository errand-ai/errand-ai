## ADDED Requirements

### Requirement: WebSocket connection to errand-cloud
The backend SHALL maintain a persistent WebSocket connection to the errand-cloud relay service for receiving forwarded webhook payloads.

#### Scenario: Connection on startup with existing credentials
- **WHEN** errand-server starts and cloud PlatformCredential exists with status "connected"
- **THEN** the backend SHALL start a background task that connects to `wss://service.errand.cloud/ws` (or custom cloud_service_url) with `Authorization: Bearer {access_token}` header
- **THEN** on successful connection, the backend SHALL publish a `cloud_status` event with status `connected`

#### Scenario: Connection on first authentication
- **WHEN** a user completes OAuth authentication with errand-cloud for the first time
- **THEN** the backend SHALL start the WebSocket client background task immediately

#### Scenario: No credentials on startup
- **WHEN** errand-server starts and no cloud PlatformCredential exists
- **THEN** the backend SHALL NOT start the WebSocket client background task

### Requirement: Message handling
The WebSocket client SHALL implement the errand-client-protocol message types.

#### Scenario: Receive webhook message
- **WHEN** the client receives a message with `type: "webhook"`
- **THEN** the client SHALL dispatch the payload to the cloud webhook dispatcher
- **THEN** after successful processing, the client SHALL send an ACK: `{"type": "ack", "id": "<message_id>"}`

#### Scenario: Receive ping message
- **WHEN** the client receives a message with `type: "ping"` containing a `ts` field
- **THEN** the client SHALL immediately respond with `{"type": "pong", "ts": <echoed_ts>}`

#### Scenario: Message deduplication
- **WHEN** the client receives a webhook message with an `id` that has already been processed in the current connection session
- **THEN** the client SHALL send an ACK but SHALL NOT re-process the payload

### Requirement: Reconnection with exponential backoff
The WebSocket client SHALL automatically reconnect on unexpected disconnections.

#### Scenario: Network error or unexpected close
- **WHEN** the WebSocket connection drops due to a network error or non-specific close code
- **THEN** the client SHALL reconnect with exponential backoff: 0-500ms, 1-2s, 2-4s, 4-8s, capped at 30s
- **THEN** the backoff counter SHALL reset on successful connection
- **THEN** a `cloud_status` event SHALL be published with status `disconnected` on disconnect and `connected` on reconnect

#### Scenario: Close code 4001 (superseded)
- **WHEN** the WebSocket is closed with code 4001
- **THEN** the client SHALL NOT auto-reconnect
- **THEN** a `cloud_status` event SHALL be published with status `disconnected` and detail "Connection taken over by another instance"

#### Scenario: Close code 4002 (auth_expired)
- **WHEN** the WebSocket is closed with code 4002
- **THEN** the client SHALL attempt to refresh the access token
- **THEN** if refresh succeeds, the client SHALL reconnect with the new token
- **THEN** if refresh fails, the client SHALL NOT auto-reconnect and SHALL set PlatformCredential status to "error"

#### Scenario: Close code 4003 (tenant_disabled)
- **WHEN** the WebSocket is closed with code 4003
- **THEN** the client SHALL NOT auto-reconnect
- **THEN** the PlatformCredential status SHALL be set to "error"
- **THEN** a `cloud_status` event SHALL be published with status `error` and detail "Account suspended"

### Requirement: Graceful shutdown
The WebSocket client SHALL shut down cleanly when the errand-server is stopping or the user disconnects.

#### Scenario: Server shutdown
- **WHEN** the errand-server lifespan exits
- **THEN** the WebSocket client task SHALL be cancelled
- **THEN** the client SHALL send a close frame with code 1000 before terminating

#### Scenario: User disconnect
- **WHEN** the user disconnects via the cloud settings page
- **THEN** the WebSocket client task SHALL be cancelled and the connection closed with code 1000
