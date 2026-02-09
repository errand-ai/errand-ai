## 1. Infrastructure — Valkey

- [x] 1.1 Add Bitnami Valkey as a subchart dependency in `helm/content-manager/Chart.yaml`
- [x] 1.2 Add Valkey configuration values in `helm/content-manager/values.yaml` (standalone mode, no persistence, resource limits)
- [x] 1.3 Add `VALKEY_URL` environment variable to backend and worker deployment templates, pointing to the Valkey service
- [x] 1.4 Add `redis[hiredis]` to `backend/requirements.txt`

## 2. Backend — Valkey client and event publishing

- [x] 2.1 Create `backend/events.py` module with a `get_valkey()` FastAPI dependency (async redis client from `VALKEY_URL`), `publish_event(event_type, task, valkey)` function, and non-blocking error handling (log warning on failure)
- [x] 2.2 Update `POST /api/tasks` in `backend/main.py` to call `publish_event("task_created", task)` after successful commit
- [x] 2.3 Update `PATCH /api/tasks/{id}` in `backend/main.py` to call `publish_event("task_updated", task)` after successful commit
- [x] 2.4 Initialize Valkey connection in the FastAPI lifespan handler and clean up on shutdown

## 3. Backend — WebSocket endpoint

- [x] 3.1 Add `WS /api/ws/tasks` endpoint in `backend/main.py` with JWT authentication via `token` query parameter (close with 4001 on invalid/missing/expired token)
- [x] 3.2 Implement Valkey pub/sub subscription per WebSocket connection — subscribe to `task_events` channel, forward messages to the WebSocket client
- [x] 3.3 Implement ping/pong keepalive (ping every 30s, close on pong timeout of 10s)
- [x] 3.4 Handle client disconnect gracefully (unsubscribe from Valkey, clean up connection)

## 4. Backend tests — WebSocket and event publishing

- [x] 4.1 Add `fakeredis[aioredis]` to `backend/requirements-test.txt`
- [x] 4.2 Update `backend/tests/conftest.py` — add a `fakeredis.aioredis.FakeRedis` fixture and override `get_valkey` dependency to inject it into the test app
- [x] 4.3 Create `backend/tests/test_events.py` — test that `POST /api/tasks` publishes a `task_created` event to the `task_events` Valkey channel with the correct task payload
- [x] 4.4 Add test that `PATCH /api/tasks/{id}` publishes a `task_updated` event to the `task_events` Valkey channel with the updated task payload
- [x] 4.5 Add test that no event is published on validation failure (422) or not-found (404)
- [x] 4.6 Create `backend/tests/test_websocket.py` — test WebSocket connection with valid token receives events when tasks are created/updated
- [x] 4.7 Add test that WebSocket connection without token is closed with code 4001
- [x] 4.8 Add test that WebSocket connection with invalid token is closed with code 4001

## 5. Worker — Event publishing

- [x] 5.1 Import and use `publish_event` from `backend/events.py` in `backend/worker.py`
- [x] 5.2 Publish `task_updated` event after transitioning task to `running`
- [x] 5.3 Publish `task_updated` event after transitioning task to `completed` or `failed`
- [x] 5.4 Initialize and clean up Valkey connection in the worker run loop

## 6. Frontend — WebSocket client

- [x] 6.1 Create `frontend/src/composables/useWebSocket.ts` — WebSocket connection manager with JWT auth via query parameter, reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s), and connection state tracking
- [x] 6.2 Update `frontend/src/stores/tasks.ts` — replace polling as primary update mechanism with WebSocket events, apply `task_created` and `task_updated` events to the local store reactively
- [x] 6.3 Implement polling fallback in `frontend/src/stores/tasks.ts` — start polling when WebSocket is disconnected, stop polling when WebSocket reconnects
- [x] 6.4 Construct WebSocket URL dynamically from current page location (wss:// for https://, ws:// for http://) with token from auth store

## 7. Frontend tests — WebSocket and store integration

- [x] 7.1 Create `frontend/src/components/__tests__/useWebSocket.test.ts` — mock global `WebSocket`, test connection lifecycle (open, message, close), auth token passed as query parameter, reconnection with backoff on close
- [x] 7.2 Create `frontend/src/components/__tests__/TasksStoreWebSocket.test.ts` — test that `task_created` WebSocket event adds a new task to the store, `task_updated` event updates an existing task in the store
- [x] 7.3 Add test that polling starts when WebSocket connection fails and stops when it reconnects

## 8. Infrastructure — Ingress and nginx

- [x] 8.1 Add `nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"` annotation to the ingress template or values to keep WebSocket connections alive
- [x] 8.2 Update `frontend/nginx.conf` to proxy `/api/ws` to the backend with WebSocket upgrade headers for local dev (`proxy_set_header Upgrade`, `proxy_set_header Connection "upgrade"`)

## 9. Verification

- [x] 9.1 Run `pytest` and `npm test` — all new and existing tests pass
- [x] 9.2 Test locally with `docker compose up --build` — verify WebSocket connection establishes, events are received on task create/update
- [x] 9.3 Test polling fallback — stop Valkey container, verify frontend falls back to polling
- [x] 9.4 Test worker events — create a task with status `pending`, verify worker transitions push events to frontend via WebSocket
- [x] 9.5 Bump `VERSION` file for the release
