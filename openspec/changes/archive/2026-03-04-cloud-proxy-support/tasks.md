## 1. SSE Endpoints

- [x] 1.1 Create `GET /api/events` SSE endpoint — StreamingResponse with async generator, subscribe to `task_events` Valkey pub/sub, forward as SSE events (task_created, task_updated, task_deleted, cloud_status)
- [x] 1.2 Add JWT authentication via `token` query parameter to `/api/events` (401 on missing/invalid/expired)
- [x] 1.3 Create `GET /api/tasks/{task_id}/logs/stream` SSE endpoint — subscribe to `task_logs:{task_id}` Valkey pub/sub, forward log lines, send task_log_end on finish
- [x] 1.4 Add JWT authentication via `token` query parameter to `/api/tasks/{task_id}/logs/stream`
- [x] 1.5 Handle non-running task (send task_log_end immediately) and non-existent task (404) for log streaming
- [x] 1.6 Write tests for SSE task events endpoint (mock Valkey pub/sub, verify event format, auth rejection)
- [x] 1.7 Write tests for SSE log streaming endpoint (mock Valkey pub/sub, verify log forwarding, non-running task, 404)

## 2. Remove WebSocket Browser Endpoints

- [x] 2.1 Remove `WS /api/ws/tasks` endpoint and its handler
- [x] 2.2 Remove `WS /api/ws/tasks/{task_id}/logs` endpoint and its handler
- [x] 2.3 Update any imports or references to the removed WebSocket handlers

## 3. Cloud-Trusted Authentication

- [x] 3.1 Create cloud JWKS fetcher — fetch and cache JWKS from cloud Keycloak realm, derive URL from cloud_service_url platform credential or JWT `iss` claim
- [x] 3.2 Create `X-Cloud-JWT` validation function — decode JWT, verify signature against cached JWKS, check expiry
- [x] 3.3 Add cloud-trusted auth to the auth dependency chain — check X-Cloud-JWT before local/SSO, only honor when request originated from proxy handler (not direct HTTP)
- [x] 3.4 Add context marker for proxy-originated requests (e.g., request state flag set by proxy handler)
- [x] 3.5 Write tests for cloud-trusted auth (valid JWT accepted, expired rejected, direct request with header ignored, audit identity extraction)

## 4. Capability Registration

- [x] 4.1 Create capability detection function — derive capabilities list from runtime configuration (transcription model, LiteLLM availability, etc.)
- [x] 4.2 Read server version from VERSION file (fallback to "unknown")
- [x] 4.3 Write tests for capability detection (full set, minimal set, version file missing)

## 5. Cloud WebSocket Client Extensions

- [x] 5.1 Add `register` message sending after WebSocket connection is established — include server_version, protocol_version, capabilities
- [x] 5.2 Wait for `registered` acknowledgement before entering main message loop
- [x] 5.3 Add `proxy_request` message handler — parse method/path/headers/body, make local HTTP request via httpx.AsyncClient, send `proxy_response` with matching id
- [x] 5.4 Add `X-Cloud-JWT` header injection into proxied requests from the proxy_request message
- [x] 5.5 Add `subscribe` message handler — subscribe to mapped Valkey pub/sub channels, start forwarding as push_event messages
- [x] 5.6 Add `unsubscribe` message handler — unsubscribe from Valkey channels, stop forwarding
- [x] 5.7 Implement reference-counted subscription management (subscribe increments, unsubscribe decrements, remove at zero)
- [x] 5.8 Add `push_event` message formatting and sending for subscribed channel events
- [x] 5.9 Write tests for register message (version, capabilities sent on connect)
- [x] 5.10 Write tests for proxy_request handler (successful request, 404, POST with body, X-Cloud-JWT forwarded)
- [x] 5.11 Write tests for subscribe/unsubscribe (channel mapping, reference counting, push_event format)

## 6. Frontend Migration to @errand/ui-components

- [x] 6.1 Add `@errand-ai/ui-components` as dependency in frontend/package.json
- [x] 6.2 Update Tailwind config to include library source in content paths
- [x] 6.3 Set up `createErrandUI` plugin in main.ts with `createDirectApi` and capabilities provider
- [x] 6.4 Replace local TaskBoard, TaskCard, TaskForm, TaskEditModal, TaskOutputModal, DeleteConfirmModal with shared library imports
- [x] 6.5 Replace local TaskLogModal with shared TaskLogViewer component (switch from WebSocket to SSE)
- [x] 6.6 Replace local App.vue header with shared HeaderBar component (mobile-responsive)
- [x] 6.7 Replace local AudioRecorder/voice input with shared component
- [x] 6.8 Update task Pinia store to use SSE EventSource instead of `useWebSocket`
- [x] 6.9 Remove old local component files that have been replaced by shared library
- [x] 6.10 Remove `useWebSocket.ts` composable (no longer needed)
- [x] 6.11 Verify frontend builds and all features work with shared components
