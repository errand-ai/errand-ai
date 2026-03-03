## Context

The errand-server currently has:
- A **WebSocket connection to errand-cloud** (`cloud-websocket-client` spec) that receives forwarded webhooks and handles ping/pong heartbeats. This is unidirectional — cloud sends webhooks, server ACKs them.
- A **WebSocket endpoint for the browser** (`WS /api/ws/tasks`) that pushes real-time task status updates (task_created, task_updated, task_deleted, cloud_status events) to the frontend.
- A **WebSocket endpoint for log streaming** (`WS /api/ws/tasks/{task_id}/logs`) that streams live task runner logs to the frontend.
- **Local auth** (backend-minted JWT) and **SSO auth** (Keycloak OIDC) modes.
- A **Vue frontend** with components for task board, settings, MCP servers, voice input, log viewer — all using direct HTTP calls and WebSocket for real-time.

This change extends the server to support remote access via the errand-cloud tunnel by: migrating browser real-time to SSE, adding cloud-trusted auth, extending the cloud WebSocket client with proxy/pub-sub handling, and refactoring the frontend to use the shared `@errand/ui-components` library.

## Goals / Non-Goals

**Goals:**

- Migrate all browser-facing real-time from WebSocket to SSE for consistency with the cloud proxy architecture
- Add a cloud-trusted auth mode that accepts Keycloak JWTs forwarded by errand-cloud
- Extend the cloud WebSocket client to handle proxy_request/response, subscribe/unsubscribe, push_event, and register messages
- Report server version and capabilities on cloud connection
- Refactor the frontend to consume `@errand/ui-components` shared library

**Non-Goals:**

- Breaking changes to the existing local or SSO auth flows
- API versioning with explicit version prefixes (capability negotiation handles this)
- Changes to the webhook relay protocol (webhook, ack, ping, pong unchanged)
- Changing the task runner or worker — only how their output reaches the browser

## Decisions

### 1. SSE implementation: FastAPI StreamingResponse with Valkey pub/sub

**Decision:** Implement SSE endpoints using FastAPI's `StreamingResponse` with `text/event-stream` content type. Each SSE connection subscribes to the relevant Valkey pub/sub channels, same as the current WebSocket endpoints.

**Rationale:** The existing WebSocket endpoints already use Valkey pub/sub internally. Switching to SSE changes only the browser transport, not the internal event routing. FastAPI's `StreamingResponse` with an async generator is the standard pattern for SSE.

**Two new endpoints:**
- `GET /api/events?token={jwt}` — replaces `WS /api/ws/tasks` for task board events
- `GET /api/tasks/{task_id}/logs/stream?token={jwt}` — replaces `WS /api/ws/tasks/{task_id}/logs`

Auth uses a `token` query parameter (same pattern as the existing WebSocket endpoints, since `EventSource` doesn't support custom headers).

**Alternatives considered:**
- WebSocket SSE bridge library — unnecessary complexity, SSE natively fits the one-way push pattern
- Keep WebSocket for local, add SSE only for cloud — two codepaths for the same functionality

### 2. Internal event bus: reuse existing Valkey pub/sub channels

**Decision:** The existing Valkey pub/sub channels (`task_events`, `task_logs:{task_id}`) remain the internal event bus. Both SSE endpoints and the cloud tunnel handler subscribe to these same channels.

**Rationale:** No new infrastructure needed. The worker already publishes to these channels. The only change is who subscribes — previously only WebSocket handlers, now SSE handlers and the cloud tunnel handler.

### 3. Cloud-trusted auth: new auth mode via X-Cloud-JWT header

**Decision:** Add a "cloud-trusted" auth mode where requests arriving through the cloud tunnel include an `X-Cloud-JWT` header containing the user's Keycloak JWT. The server validates this JWT against the errand-cloud Keycloak realm's JWKS endpoint.

**Rationale:** Solo users don't configure OIDC on their local server. The cloud JWT carries the user identity for audit trails. The trust boundary is the WebSocket tunnel (already authenticated when the server connected to cloud).

**Implementation:**
- The proxy request handler adds `X-Cloud-JWT` to forwarded requests
- The auth dependency chain checks for `X-Cloud-JWT` before falling back to local/SSO auth
- JWKS endpoint URL is derived from the cloud service URL (already configured as `cloud_service_url` in platform credentials)
- JWT validation uses the same `jwt.decode()` + JWKS pattern as errand-cloud itself

**Alternatives considered:**
- Pass-through service account token — loses user identity for audit
- Mutual TLS between cloud and server — overcomplicated for WebSocket tunnel
- Server trusts any request from the tunnel without JWT — no audit trail

### 4. Capability registration: derive from feature configuration

**Decision:** On WebSocket connect, the server sends a `register` message with its version (from `VERSION` file) and a capabilities list derived from runtime configuration.

**Capabilities are determined by:**
- Always present: `tasks`, `settings`
- Present if MCP servers configured: `mcp-servers`
- Present if transcription model configured: `voice-input`
- Present if task profiles exist: `task-profiles`
- Present if LiteLLM proxy detected: `litellm-mcp`
- Present if platforms configured: `platforms`

**Rationale:** Capabilities are dynamic — they depend on what the user has configured, not just what version is installed. A server at version 0.17.0 might not have `voice-input` if no transcription model is set up.

### 5. Proxy request handler: local HTTP self-call

**Decision:** When the cloud tunnel client receives a `proxy_request` message, it makes an HTTP request to the server's own API (via `httpx.AsyncClient` calling `localhost:{port}`), forwarding the method, path, headers (including `X-Cloud-JWT`), and body. The response is packaged as a `proxy_response` message.

**Rationale:** This reuses all existing API handlers, middleware, and auth logic without modification. The proxy handler is a thin HTTP client, not a reimplementation of any endpoint logic.

**Alternatives considered:**
- ASGI direct dispatch (calling the app internally) — tighter coupling, harder to test, doesn't go through middleware stack
- Separate proxy endpoint handlers — duplicates every API handler

### 6. Subscribe/unsubscribe: reference-counted channel subscriptions

**Decision:** The tunnel handler maintains a `subscriptions: dict[str, int]` mapping channel names to reference counts. `subscribe` increments, `unsubscribe` decrements, and when a count reaches zero the Valkey pub/sub subscription is removed. Active subscriptions forward events as `push_event` messages.

**Rationale:** The cloud may open multiple browser SSE connections that need the same channel. Reference counting ensures we only subscribe/unsubscribe at the Valkey level when truly needed.

### 7. Frontend migration: consume @errand/ui-components

**Decision:** Replace local component implementations with imports from `@errand/ui-components`. Provide the direct HTTP `ErrandApi` implementation and wire up SSE-based `useEventStream` composable (pointing at the new SSE endpoints). Keep app shell (routing, auth, Pinia stores) local.

**Rationale:** The shared library provides the same components currently in the frontend, extracted for reuse. The migration is primarily import path changes and removing duplicated code.

## Risks / Trade-offs

**[SSE migration breaks existing clients]** → The WebSocket endpoints will be removed. Any client using `WS /api/ws/tasks` or `WS /api/ws/tasks/{task_id}/logs` will need to switch to the SSE equivalents. Mitigate by doing the frontend migration in the same change, and documenting the API change.

**[Proxy request latency]** → Each proxied API call goes through the WebSocket tunnel, adding network round-trip time. For a user on home broadband this is typically 20-50ms. Mitigate by keeping the proxy path thin (no extra processing) and ensuring the UI feels responsive despite the latency.

**[Cloud JWKS endpoint availability]** → If errand-cloud's Keycloak is unreachable, cloud-trusted auth fails. Mitigate by caching the JWKS with a TTL (same pattern errand-cloud uses), so brief outages don't break auth.

**[Capability registration accuracy]** → If capabilities don't accurately reflect what the server supports, the cloud UI may show features that don't work (or hide features that do). Mitigate by deriving capabilities from actual configuration state at registration time, and re-registering when configuration changes.

## Migration Plan

1. Add SSE endpoints alongside existing WebSocket endpoints
2. Migrate frontend to use SSE via `@errand/ui-components`
3. Remove old WebSocket endpoints (`/api/ws/tasks`, `/api/ws/tasks/{task_id}/logs`)
4. Add cloud-trusted auth mode
5. Extend cloud WebSocket client with register, proxy, subscribe/unsubscribe handlers
6. Test end-to-end with errand-cloud proxy
