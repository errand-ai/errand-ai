## REMOVED Requirements

### Requirement: WebSocket endpoint for per-task log streaming

**Reason:** Replaced by SSE endpoint at `GET /api/tasks/{task_id}/logs/stream`. SSE provides a simpler, consistent transport for all server-to-browser push, aligning with the cloud proxy architecture.

**Migration:** Clients SHALL use `GET /api/tasks/{task_id}/logs/stream?token={jwt}` (SSE) instead of `WS /api/ws/tasks/{task_id}/logs?token={jwt}` (WebSocket).

### Requirement: Log streaming WebSocket authentication

**Reason:** Replaced by authentication on the SSE log streaming endpoint.

**Migration:** The SSE endpoint uses the same `token` query parameter pattern. No change in auth approach, only transport.
