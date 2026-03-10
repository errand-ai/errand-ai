## ADDED Requirements

### Requirement: Reconnect on supersession close code

The `CloudWebSocketClient` SHALL reconnect with exponential backoff when the WebSocket is closed with code 4001 (superseded), instead of permanently stopping.

The client SHALL stop permanently only after receiving 5 consecutive 4001 close codes without a successful message exchange in between.

#### Scenario: Single 4001 close during deployment

- **WHEN** the WebSocket connection is closed with code 4001
- **THEN** the client SHALL reconnect with exponential backoff
- **AND** the backoff attempt counter SHALL increment

#### Scenario: Successful reconnect resets eviction counter

- **WHEN** the client reconnects after a 4001 close and successfully completes the register/registered handshake
- **THEN** the consecutive eviction counter SHALL reset to zero

#### Scenario: Repeated 4001 closes exceed threshold

- **WHEN** the client receives 5 consecutive 4001 close codes without a successful message exchange
- **THEN** the client SHALL stop permanently
- **AND** publish a `cloud_status` event with status `disconnected` and detail indicating repeated evictions

### Requirement: Liveness watchdog

The `CloudWebSocketClient` SHALL detect dead connections by monitoring the time since the last received message.

The watchdog timeout SHALL be 90 seconds (3x the cloud server's 30-second ping interval).

#### Scenario: No messages received within timeout

- **WHEN** no message (of any type, including ping) is received for 90 seconds
- **THEN** the client SHALL close the WebSocket connection
- **AND** trigger a reconnection with exponential backoff

#### Scenario: Messages received within timeout

- **WHEN** messages are received within the 90-second window
- **THEN** the watchdog timer SHALL reset after each received message
- **AND** the connection SHALL remain open

### Requirement: Immediate status cleanup on disconnect

The `CloudWebSocketClient` SHALL update its connection status immediately when the WebSocket disconnects, regardless of the close reason.

#### Scenario: Connection drops unexpectedly

- **WHEN** `_connect_and_receive()` returns or raises for any reason
- **THEN** `_ws_connected` SHALL be set to `False`
- **AND** `self._ws` SHALL be set to `None`
- **AND** a `cloud_status` event with status `disconnected` SHALL be published
- **AND** this SHALL happen before the backoff sleep

#### Scenario: Normal close code processing

- **WHEN** the connection is closed with a recognized close code (4001, 4002, 4003)
- **THEN** the status cleanup SHALL occur in addition to code-specific handling
