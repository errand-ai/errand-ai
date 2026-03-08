## MODIFIED Requirements

### Requirement: Subscribe and unsubscribe handling

The WebSocket client SHALL handle `subscribe` and `unsubscribe` messages to manage real-time event forwarding through the tunnel.

On `subscribe`:
- For each channel in the channels array, subscribe to the corresponding Valkey pub/sub channel
- Forward events from subscribed channels as `push_event` messages

On `unsubscribe`:
- For each channel in the channels array, unsubscribe from the Valkey pub/sub channel
- Stop forwarding events for those channels

Channel mapping:
- `tasks` → Valkey channel `task_events`
- `logs:{task_id}` → Valkey channel `task_logs:{task_id}`
- `system` → Valkey channel `system_events`

#### Scenario: Subscribe to task events

- **WHEN** the client receives `{"type": "subscribe", "channels": ["tasks"]}`
- **THEN** the client subscribes to the `task_events` Valkey pub/sub channel
- **AND** forwards events as `{"type": "push_event", "channel": "tasks", "data": {...}}`

#### Scenario: Subscribe to log streaming

- **WHEN** the client receives `{"type": "subscribe", "channels": ["logs:42"]}`
- **THEN** the client subscribes to the `task_logs:42` Valkey pub/sub channel
- **AND** forwards log lines as `{"type": "push_event", "channel": "logs:42", "data": "..."}`

#### Scenario: Unsubscribe stops forwarding

- **WHEN** the client receives `{"type": "unsubscribe", "channels": ["tasks"]}`
- **THEN** the client unsubscribes from the `task_events` Valkey channel
- **AND** stops forwarding task events

#### Scenario: No subscriptions means no event forwarding

- **WHEN** no subscribe messages have been received (or all channels unsubscribed)
- **THEN** no push_event messages are sent through the tunnel

### Requirement: Subscription alert handling in pubsub loop

The WebSocket client's pubsub loop SHALL handle `subscription_alert` messages from the `tenant:{id}:notify` channel as structured JSON events rather than triggering webhook drain.

#### Scenario: Subscription alert received on notify channel
- **WHEN** the pubsub loop receives a message on `tenant:{id}:notify` with valid JSON containing `"type": "subscription_alert"`
- **THEN** the client SHALL NOT trigger webhook drain for this message
- **THEN** the client SHALL forward the alert payload to errand-desktop via the existing WebSocket event mechanism as a `push_event` with channel `system`

#### Scenario: Non-alert message on notify channel
- **WHEN** the pubsub loop receives a message on `tenant:{id}:notify` that is not valid JSON or does not have `"type": "subscription_alert"`
- **THEN** the client SHALL handle it via the existing webhook drain logic

#### Scenario: Subscription alert forwarded to desktop
- **WHEN** a `subscription_alert` message is received and the `system` channel is subscribed
- **THEN** the client SHALL send `{"type": "push_event", "channel": "system", "data": {"type": "subscription_alert", "alert": "...", ...}}`
