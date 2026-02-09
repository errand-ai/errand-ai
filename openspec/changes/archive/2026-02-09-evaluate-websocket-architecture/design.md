## Context

The frontend polls `GET /api/tasks` every 5 seconds (`POLL_INTERVAL = 5000` in `stores/tasks.ts`) to keep the Kanban board in sync. The backend is a stateless FastAPI app (potentially multiple replicas) fronted by an nginx ingress. A separate worker process polls PostgreSQL for pending tasks, transitions them through `running` → `completed`/`failed`, and writes directly to the database (not via the API).

Current data flow:
1. Frontend creates/updates tasks via REST API (`POST /api/tasks`, `PATCH /api/tasks/{id}`)
2. Worker dequeues pending tasks from PostgreSQL, processes them, writes status back to DB
3. Frontend polls `GET /api/tasks` every 5s to see all changes

The polling approach means UI updates lag by up to 5 seconds and every connected client generates a full task list query every 5 seconds regardless of whether anything changed.

## Goals / Non-Goals

**Goals:**
- Deliver real-time task state updates to connected frontends via WebSocket push
- Use Valkey (Redis-compatible) pub/sub as the cross-process and cross-replica event bus
- Both the API server (on task create/update) and the worker (on status transitions) publish events
- Maintain REST API for all CRUD operations — WebSocket is event notification only
- Graceful degradation: fall back to polling if WebSocket connection fails

**Non-Goals:**
- Sending commands over WebSocket (create/update tasks) — REST stays the command interface
- Per-user filtering of events (all connected clients receive all task events)
- Guaranteed delivery / event replay / offline sync — this is a live notification channel, not a queue
- Replacing the worker's database-based task dequeue with Valkey-based queueing

## Decisions

### 1. WebSocket endpoint on the backend API server

**Decision**: Add `WS /api/ws/tasks` to the FastAPI app.

**Rationale**: FastAPI/Starlette has native WebSocket support. Placing it under `/api` means the existing ingress path rule (`/api → backend`) routes WebSocket upgrades to the backend without additional ingress config. The nginx ingress controller handles `Upgrade: websocket` headers by default for matched paths.

**Alternatives considered**:
- Dedicated WebSocket service — adds operational complexity for no benefit at current scale
- Server-Sent Events (SSE) — simpler but unidirectional (server→client only), no native reconnection token, and less ecosystem support in Python async frameworks

### 2. Valkey as the pub/sub broker

**Decision**: Use Valkey (Redis-compatible, Apache-2.0 licensed) for pub/sub event broadcasting.

**Rationale**: The backend is stateless with potentially multiple replicas. In-process pub/sub (e.g. Python `asyncio.Queue` or a broadcast set) only reaches WebSocket clients connected to the same replica. Valkey pub/sub provides cross-replica fan-out: any process that publishes an event reaches all subscribing processes. The `redis` Python package (`redis[hiredis]`) is fully compatible with Valkey.

**Alternatives considered**:
- PostgreSQL NOTIFY/LISTEN — works but payload limited to 8000 bytes, connection-pool friction with async SQLAlchemy, and mixes concerns with the data store
- In-process only — breaks with >1 replica

### 3. Event publishing from both API and worker

**Decision**: Both `main.py` (API endpoints) and `worker.py` publish task events to a Valkey channel after successful database writes. The Valkey client is exposed as a FastAPI dependency (`get_valkey()`) in `events.py`, making it overridable in tests via the same `app.dependency_overrides` pattern used for `get_session` and `get_current_user`.

**Rationale**: The worker bypasses the API and writes directly to PostgreSQL. If only the API published events, worker-driven transitions (pending → running → completed) would not be pushed to frontends. Both processes need a Valkey client. Making the client a FastAPI dependency follows the established testing pattern in `conftest.py` where dependencies are overridden with test doubles.

**Event publish points**:
- `POST /api/tasks` → publish `task_created` after commit
- `PATCH /api/tasks/{id}` → publish `task_updated` after commit
- `worker.py` status transitions → publish `task_updated` after each commit

### 4. Event message format

**Decision**: JSON messages on the WebSocket with the structure:
```json
{
  "event": "task_created" | "task_updated",
  "task": { "id": "...", "title": "...", "status": "...", "created_at": "...", "updated_at": "..." }
}
```

**Rationale**: Sending the full task object avoids the frontend needing a follow-up GET request. The payload matches the existing `TaskResponse` schema so the frontend can directly update its store.

### 5. WebSocket authentication via query parameter

**Decision**: The WebSocket connection authenticates via a `token` query parameter: `ws://host/api/ws/tasks?token=<jwt>`.

**Rationale**: The browser WebSocket API does not support custom headers (no `Authorization: Bearer` header). The standard workaround is passing the token as a query parameter. The backend validates the JWT on connection handshake and closes with 4001 if invalid/expired.

**Alternatives considered**:
- Cookie-based auth — the app uses token-based auth, not cookies
- First-message auth — adds protocol complexity and a window where the connection is unauthenticated

### 6. Frontend reconnection with polling fallback

**Decision**: The frontend task store attempts WebSocket connection on mount. On disconnect, it retries with exponential backoff. If the WebSocket is unavailable (e.g. feature not deployed yet, network issue), it falls back to the existing 5s polling.

**Rationale**: Ensures the app remains functional during rollout and in degraded network conditions. Polling is already implemented and tested.

### 7. Testing strategy

**Decision**: Follow the established test patterns from `add-scenario-tests`: pytest + httpx AsyncClient for backend, Vitest + Vue Test Utils for frontend. Use `fakeredis[aioredis]` to mock Valkey in backend tests. Use a mock WebSocket in frontend tests.

**Backend — Valkey mocking**: The `events.py` module exposes a `get_valkey()` dependency (async Redis client). In tests, `conftest.py` overrides this dependency with a `fakeredis.aioredis.FakeRedis` instance. This allows tests to verify that events are published to the correct channel with the correct payload without needing a real Valkey instance. The same `fakeredis` instance can be used to subscribe and assert on published messages.

**Backend — WebSocket endpoint testing**: Use Starlette's `TestClient` WebSocket support (`client.websocket_connect("/api/ws/tasks?token=...")`) to test the WebSocket lifecycle. The test creates a task via the REST API, then asserts that the WebSocket receives the corresponding event. Auth rejection tests verify that missing/invalid tokens result in a 4001 close code. The `fakeredis` pub/sub ensures events flow from REST endpoint → Valkey → WebSocket in-process.

**Frontend — WebSocket mocking**: Mock the global `WebSocket` constructor in Vitest to simulate connection, message delivery, and disconnection. Test that the task store applies `task_created`/`task_updated` events correctly and that polling fallback activates on WebSocket failure.

**CI**: Add `fakeredis[aioredis]` to `requirements-test.txt`. No real Valkey needed in CI — all tests use fakes. The existing CI `test` job structure (pip install + pytest, npm ci + npm test) remains unchanged.

### 8. Valkey Helm deployment

**Decision**: Add Valkey as a subchart dependency in the Helm chart using the Bitnami Valkey chart (`oci://registry-1.docker.io/bitnamicharts/valkey`).

**Rationale**: Bitnami provides a maintained, production-ready Helm chart. Valkey is a drop-in Redis replacement — the only config needed is the connection URL passed to backend/worker pods via environment variable.

## Risks / Trade-offs

**[WebSocket connection scaling]** → Long-lived WebSocket connections consume memory per connection on the backend pod. At current scale (small number of users) this is not a concern. If it becomes one, horizontal scaling (more replicas) distributes connections, and Valkey pub/sub ensures all replicas receive events.

**[Valkey as new infrastructure dependency]** → Adds a component that needs monitoring and can fail. Mitigation: polling fallback means the app degrades gracefully if Valkey is down. Valkey itself is lightweight and the Bitnami chart supports persistence and health checks.

**[Worker needs Valkey client]** → The worker currently has no external dependencies beyond PostgreSQL. Adding a Valkey client (`redis[hiredis]`) is a small addition. If the Valkey connection fails, the worker should still function (task processing continues, just no push notifications). Publish failures should be logged but not block task processing.

**[Token expiry on long-lived WebSocket]** → JWTs expire but WebSocket connections persist. Mitigation: the backend checks token expiry on connect only (not per-message). The frontend reconnects on close, and the auth store handles token refresh. A future enhancement could add periodic token validation or client-initiated re-auth messages.

**[Ingress WebSocket timeout]** → nginx ingress has a default `proxy-read-timeout` of 60s which would drop idle WebSocket connections. Mitigation: add a `proxy-read-timeout` annotation on the ingress (e.g. 3600s) and implement ping/pong keepalives.

## Migration Plan

1. **Phase 1**: Deploy Valkey via Helm subchart. No app changes — Valkey runs idle.
2. **Phase 2**: Deploy backend with WebSocket endpoint + Valkey publishing. REST API continues working. Frontend still polls.
3. **Phase 3**: Deploy frontend with WebSocket client. Falls back to polling if WebSocket connection fails.
4. **Phase 4**: Deploy worker with Valkey publishing for status transitions.

**Rollback**: Each phase is independently deployable. Removing WebSocket code from frontend reverts to polling. Removing Valkey publishing from backend/worker has no impact on functionality. Valkey subchart can be disabled.

## Open Questions

- **Valkey persistence**: Do we need Valkey persistence (RDB/AOF) or is ephemeral sufficient? Since pub/sub messages are fire-and-forget (no replay), ephemeral should be fine.
- **Valkey resource limits**: What CPU/memory limits for the Valkey pod? Pub/sub is lightweight — minimal resources should suffice.
