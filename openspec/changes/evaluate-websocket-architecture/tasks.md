## 1. Infrastructure — Valkey

- [ ] 1.1 Add Bitnami Valkey as a subchart dependency in `helm/content-manager/Chart.yaml`
- [ ] 1.2 Add Valkey configuration values in `helm/content-manager/values.yaml` (standalone mode, no persistence, resource limits)
- [ ] 1.3 Add `VALKEY_URL` environment variable to backend and worker deployment templates, pointing to the Valkey service
- [ ] 1.4 Add `redis[hiredis]` to `backend/requirements.txt`

## 2. Backend — Valkey client and event publishing

- [ ] 2.1 Create `backend/events.py` module with Valkey client setup (async redis connection from `VALKEY_URL`), `publish_event(event_type, task)` function, and non-blocking error handling (log warning on failure)
- [ ] 2.2 Update `POST /api/tasks` in `backend/main.py` to call `publish_event("task_created", task)` after successful commit
- [ ] 2.3 Update `PATCH /api/tasks/{id}` in `backend/main.py` to call `publish_event("task_updated", task)` after successful commit
- [ ] 2.4 Initialize Valkey connection in the FastAPI lifespan handler and clean up on shutdown

## 3. Backend — WebSocket endpoint

- [ ] 3.1 Add `WS /api/ws/tasks` endpoint in `backend/main.py` with JWT authentication via `token` query parameter (close with 4001 on invalid/missing/expired token)
- [ ] 3.2 Implement Valkey pub/sub subscription per WebSocket connection — subscribe to `task_events` channel, forward messages to the WebSocket client
- [ ] 3.3 Implement ping/pong keepalive (ping every 30s, close on pong timeout of 10s)
- [ ] 3.4 Handle client disconnect gracefully (unsubscribe from Valkey, clean up connection)

## 4. Worker — Event publishing

- [ ] 4.1 Import and use `publish_event` from `backend/events.py` in `backend/worker.py`
- [ ] 4.2 Publish `task_updated` event after transitioning task to `running`
- [ ] 4.3 Publish `task_updated` event after transitioning task to `completed` or `failed`
- [ ] 4.4 Initialize and clean up Valkey connection in the worker run loop

## 5. Frontend — WebSocket client

- [ ] 5.1 Create `frontend/src/composables/useWebSocket.ts` — WebSocket connection manager with JWT auth via query parameter, reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s), and connection state tracking
- [ ] 5.2 Update `frontend/src/stores/tasks.ts` — replace polling as primary update mechanism with WebSocket events, apply `task_created` and `task_updated` events to the local store reactively
- [ ] 5.3 Implement polling fallback in `frontend/src/stores/tasks.ts` — start polling when WebSocket is disconnected, stop polling when WebSocket reconnects
- [ ] 5.4 Construct WebSocket URL dynamically from current page location (wss:// for https://, ws:// for http://) with token from auth store

## 6. Infrastructure — Ingress and nginx

- [ ] 6.1 Add `nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"` annotation to the ingress template or values to keep WebSocket connections alive
- [ ] 6.2 Update `frontend/nginx.conf` to proxy `/api/ws` to the backend with WebSocket upgrade headers for local dev (`proxy_set_header Upgrade`, `proxy_set_header Connection "upgrade"`)

## 7. Verification

- [ ] 7.1 Test locally with `docker compose up --build` — verify WebSocket connection establishes, events are received on task create/update
- [ ] 7.2 Test polling fallback — stop Valkey container, verify frontend falls back to polling
- [ ] 7.3 Test worker events — create a task with status `pending`, verify worker transitions push events to frontend via WebSocket
- [ ] 7.4 Bump `VERSION` file for the release
