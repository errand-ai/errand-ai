## ADDED Requirements

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
