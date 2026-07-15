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

### Requirement: Subscription alert handling

The WebSocket client SHALL handle `subscription_alert` messages relayed by errand-cloud over the WebSocket tunnel, dispatched by `type` in `_handle_message` alongside the existing message types (`webhook`, `proxy_request`, `oauth_tokens`, …).

#### Scenario: Subscription alert received over the tunnel
- **WHEN** the client receives a tunnel message with `"type": "subscription_alert"`
- **THEN** the client SHALL route it to the subscription-alert handler rather than any other message branch
- **THEN** the client SHALL forward the alert payload to errand-desktop as a `push_event` on the `system` channel when that channel is subscribed (see the forwarding scenario below)

#### Scenario: Non-alert message over the tunnel
- **WHEN** the client receives a tunnel message whose `type` is not `subscription_alert` (e.g. `webhook`), or a non-JSON frame
- **THEN** the message SHALL be handled by its existing branch (non-JSON frames are rejected before dispatch, `webhook` messages still dispatch and ACK as before)

#### Scenario: Subscription alert forwarded to desktop
- **WHEN** a `subscription_alert` message is received and the `system` channel is subscribed
- **THEN** the client SHALL send `{"type": "push_event", "channel": "system", "data": {"type": "subscription_alert", "alert": "...", ...}}`
