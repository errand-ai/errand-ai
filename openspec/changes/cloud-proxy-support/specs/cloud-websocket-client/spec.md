## ADDED Requirements

### Requirement: Registration message on connect

After the WebSocket connection to errand-cloud is established and authenticated, the client SHALL send a `register` message:

```json
{
  "type": "register",
  "server_version": "0.14.0",
  "protocol_version": 2,
  "capabilities": ["tasks", "settings", "mcp-servers", ...]
}
```

The server version SHALL be read from the `VERSION` file. Capabilities SHALL be derived from runtime configuration (see capability-registration spec).

The client SHALL wait for a `registered` acknowledgement from the cloud before processing other messages.

#### Scenario: Register on connect

- **WHEN** the WebSocket connection to errand-cloud is established
- **THEN** the client sends a `register` message with the server version and current capabilities
- **AND** waits for a `registered` response before entering the main message loop

#### Scenario: Re-register on reconnect

- **WHEN** the client reconnects after a disconnection
- **THEN** the client sends a fresh `register` message with potentially updated capabilities

### Requirement: Proxy request handling

The WebSocket client SHALL handle `proxy_request` messages from errand-cloud by making local HTTP requests to the server's own API.

When a `proxy_request` is received:
1. Extract method, path, headers, body from the message
2. Add `X-Cloud-JWT` header from the message's JWT field
3. Make an HTTP request to `http://localhost:{port}{path}` using `httpx.AsyncClient`
4. Package the response (status, headers, body) as a `proxy_response` message with the same `id`
5. Send the `proxy_response` via WebSocket

#### Scenario: Successful proxy request

- **WHEN** the client receives `{"type": "proxy_request", "id": "abc", "method": "GET", "path": "/api/tasks", "headers": {...}, "body": null}`
- **THEN** the client makes `GET http://localhost:{port}/api/tasks` with the forwarded headers
- **AND** sends `{"type": "proxy_response", "id": "abc", "status": 200, "headers": {...}, "body": "[...]"}`

#### Scenario: Proxy request to non-existent endpoint

- **WHEN** the client receives a proxy_request for a path that returns 404
- **THEN** the client sends a proxy_response with status 404

#### Scenario: Proxy request with body

- **WHEN** the client receives a proxy_request with method POST and a non-null body
- **THEN** the client forwards the body in the local HTTP request

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

### Requirement: Push event message format

Events forwarded through the tunnel SHALL use the `push_event` message type:

```json
{
  "type": "push_event",
  "channel": "tasks",
  "data": { "event": "task_updated", "task": { ... } }
}
```

#### Scenario: Task event forwarded

- **WHEN** the `task_events` Valkey channel receives a task_updated event
- **AND** the "tasks" channel is subscribed
- **THEN** the client sends a push_event with channel "tasks" and the event data
