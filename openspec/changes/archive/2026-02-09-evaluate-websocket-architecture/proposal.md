## Why

The frontend currently polls `GET /api/tasks` every 5 seconds to detect changes made by backend workers or other users. This is wasteful — most polls return unchanged data — and introduces up to 5 seconds of latency before the UI reflects state changes. As the number of connected clients grows, polling multiplies redundant HTTP requests against the backend and database. A WebSocket-based push architecture would deliver updates instantly and eliminate unnecessary load.

## What Changes

- Add a WebSocket endpoint (`/api/ws/tasks`) on the backend that pushes task change events to connected clients in real time
- Implement a pub/sub mechanism so that task mutations (create, update) broadcast events to all connected WebSocket clients
- Replace the frontend's `setInterval`-based polling in the task store with a WebSocket connection that receives push events
- Retain the REST API endpoints (`GET/POST/PATCH /api/tasks`) for task CRUD operations — WebSocket is for event delivery only, not for commands
- Keep polling as a fallback when WebSocket connection fails or is unavailable (graceful degradation)
- Handle WebSocket authentication using the existing JWT token

## Capabilities

### New Capabilities
- `websocket-events`: Backend WebSocket endpoint for real-time task event delivery, including connection lifecycle management, authentication, pub/sub broadcasting, and event message format

### Modified Capabilities
- `kanban-frontend`: Replace polling-based live state updates with WebSocket-driven event handling, with polling as fallback
- `task-api`: Backend task mutation endpoints (POST, PATCH) must emit events to the WebSocket pub/sub channel after successful writes

## Impact

- **Backend (`main.py`)**: New WebSocket endpoint, event broadcasting after task mutations, connection management
- **Backend dependencies**: May need additional packages for WebSocket pub/sub (FastAPI has native WebSocket support via Starlette; multi-replica broadcast needs a shared channel — Valkey as the pub/sub broker)
- **Frontend (`stores/tasks.ts`)**: Replace `setInterval` polling with WebSocket client, handle reconnection and fallback to polling
- **Infrastructure**: WebSocket connections are long-lived — nginx ingress must support WebSocket upgrades (`Upgrade` and `Connection` headers); uvicorn already supports WebSockets via `uvicorn[standard]`
- **Multi-replica consideration**: The current backend is stateless with multiple replicas behind a load balancer. In-process pub/sub only reaches clients connected to the same replica. Valkey (open-source Redis-compatible fork) provides cross-replica pub/sub broadcasting
- **Helm chart**: New Valkey dependency for pub/sub broker (lightweight, Redis-compatible, no license concerns)
- **KEDA**: No impact — queue metrics endpoint remains unchanged
