# Cloud Proxy Support

## Problem

The errand-server currently has no mechanism for being accessed remotely through the errand-cloud relay service. The existing WebSocket connection to errand-cloud is unidirectional — it only receives webhooks. Solo users running errand-server locally (behind home broadband, NAT, firewalls) cannot access their server when away from home.

Additionally, the server uses WebSocket connections to push real-time updates (task status changes, live log streaming) to the browser. For consistency with the cloud proxy architecture — where all real-time data flows through SSE on the browser side — the server should migrate to SSE for all browser-facing real-time push.

## Proposal

Extend the errand-server to support being accessed remotely via the errand-cloud tunnel. This involves changes across four areas:

### 1. Migrate browser real-time updates from WebSocket to SSE

Replace the current WebSocket-based real-time push to the browser with Server-Sent Events:

- **Task status events**: New SSE endpoint (`GET /api/events`) replaces `WS /api/ws/tasks`. Pushes `task_created`, `task_updated`, `task_deleted`, `cloud_status` events.
- **Live task log streaming**: New SSE endpoint (`GET /api/tasks/{task_id}/logs/stream`) replaces `WS /api/ws/tasks/{task_id}/logs`. Streams log lines in real-time for running tasks.
- **Internal event bus**: Both SSE endpoints and the cloud tunnel handler subscribe to the same internal pub/sub mechanism (Valkey pub/sub channels), ensuring consistent behavior whether accessed locally or via cloud.

The existing polling fallback remains for browsers that don't support SSE (unlikely but safe).

### 2. Cloud-trusted authentication mode

Add a new auth mode where the server trusts a Keycloak JWT forwarded by errand-cloud:

- When a proxy request arrives through the cloud tunnel, it includes the user's Keycloak JWT in an `X-Cloud-JWT` header.
- The server validates this JWT against the errand-cloud Keycloak realm's JWKS endpoint (fetched and cached, same pattern as errand-cloud's own JWT validation).
- The authenticated user identity from the JWT is used for audit logging (task creation, etc.).
- This mode requires no local user configuration — the cloud JWT is sufficient for a solo user.
- The trust boundary is the WebSocket tunnel itself (already authenticated when the server connected to cloud).

### 3. Capability registration on cloud connect

When the server connects to errand-cloud via WebSocket, it sends a `register` message:

```json
{
  "type": "register",
  "server_version": "0.14.0",
  "protocol_version": 2,
  "capabilities": ["tasks", "mcp-servers", "settings", "voice-input", ...]
}
```

- Capabilities are derived from the server's current feature set and configuration (e.g., `voice-input` only if a transcription model is configured).
- The server version is read from the existing `VERSION` file.
- The cloud stores these capabilities and uses them to gate UI features.

### 4. Proxy request handler in cloud WebSocket client

Extend the existing cloud WebSocket client (`cloud-websocket-client` spec) to handle new message types:

- **`proxy_request`**: Receive an HTTP request from the cloud, execute it locally against the server's own API (as an HTTP call to self), and return the response as a `proxy_response` message. The `X-Cloud-JWT` header is forwarded to authenticate the request.
- **`subscribe`**: Start forwarding events from specified channels (e.g., `tasks`, `logs:42`) through the tunnel as `push_event` messages.
- **`unsubscribe`**: Stop forwarding events for specified channels.

The handler only forwards events when the cloud has active subscriptions, conserving bandwidth on the user's broadband connection.

### 5. Consume @errand/ui-components

Refactor the existing Vue frontend to consume the shared `@errand/ui-components` library:

- Replace local component implementations with shared library components
- Provide the direct HTTP `ErrandApi` implementation via Vue provide/inject
- Provide SSE-based `useEventStream` composable (connecting directly to the new SSE endpoints)
- Maintain app shell, routing, auth, and Pinia stores locally

## Scope

- SSE endpoints for task events and live log streaming
- Internal event bus (Valkey pub/sub) for consistent real-time delivery
- Cloud-trusted JWT auth mode
- Capability registration in cloud WS client
- Proxy request/response handler in cloud WS client
- Subscribe/unsubscribe handling with push_event forwarding
- Frontend migration to `@errand/ui-components`
- Remove old WebSocket endpoints for browser real-time (`/api/ws/tasks`, `/api/ws/tasks/{id}/logs`)

## Non-goals

- API versioning across breaking changes (deferred until actually needed; capability negotiation handles feature presence/absence)
- Changes to the webhook relay protocol (webhook, ack, ping, pong remain unchanged)
- Changes to local auth or SSO flows (cloud-trusted is an additional mode, not a replacement)

## Dependencies

- `@errand/ui-components` shared library (shared-ui-components change) must be published first

## Protocol messages handled (new)

| Direction | Type | Purpose |
|-----------|------|---------|
| cloud → server | `proxy_request` | HTTP request to forward to local API |
| server → cloud | `proxy_response` | HTTP response from local API |
| cloud → server | `subscribe` | Start forwarding events for channels |
| cloud → server | `unsubscribe` | Stop forwarding events for channels |
| server → cloud | `push_event` | Real-time event for a subscribed channel |
| server → cloud | `register` | Version + capabilities on connect |
| cloud → server | `registered` | Acknowledgement with cloud config |
