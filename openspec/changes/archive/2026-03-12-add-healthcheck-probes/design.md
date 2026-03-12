## Context

The errand server already exposes `GET /api/health` which checks DB connectivity. However, this endpoint is not referenced by any orchestration layer. The worker process (`worker.py`) is a long-running asyncio poll loop with no HTTP interface — Kubernetes and Docker Compose have no way to determine if it's alive and functioning.

Currently:
- Server deployment has no K8s probes → K8s won't restart a hung server
- Worker deployment has no K8s probes → K8s won't restart a stuck worker
- Docker Compose `errand` and `worker` services have no healthchecks → `depends_on: condition: service_healthy` can't be used

## Goals / Non-Goals

**Goals:**
- K8s can detect and restart unresponsive server and worker containers
- Docker Compose can gate downstream services on errand/worker readiness
- Health checks verify actual functionality (DB connectivity), not just process existence

**Non-Goals:**
- Deep health checks (checking every external dependency like LiteLLM, Hindsight, etc.)
- Metrics or observability endpoints (Prometheus, etc.)
- Health dashboard or UI component

## Decisions

### 1. Worker health endpoint: background thread with stdlib HTTP server

The worker is a single-threaded asyncio process. Rather than converting it to a web framework, we'll start a lightweight `http.server` in a daemon thread before the main poll loop. This serves `GET /health` on a configurable port (default `8080`).

**Why not alternatives:**
- **File-based probe (touch a file)**: Requires an `exec` probe in K8s which is slower and heavier than `httpGet`. Also doesn't verify the process is actually responsive.
- **Adding FastAPI/uvicorn to worker**: Massive overkill for a single endpoint. Adds complexity and dependency weight.
- **TCP socket probe**: Only verifies the port is open, not that the worker logic is running.

The health handler will:
- Return 200 `{"status": "ok"}` if `shutdown_requested` is False (worker loop is active)
- Return 503 if shutdown has been requested (graceful drain)

### 2. Server probes: use existing `/api/health`

The existing endpoint already performs a `SELECT 1` against the database and returns 200/503. This is suitable for both liveness and readiness:
- **Readiness**: 200 means the server can serve traffic (DB is reachable)
- **Liveness**: 200 means the process is responsive (not deadlocked)

### 3. Probe timing configuration

Use conservative defaults that work for both local dev and production:
- `initialDelaySeconds: 10` — give the app time to start
- `periodSeconds: 15` — check every 15s
- `timeoutSeconds: 5` — fail fast on unresponsive
- `failureThreshold: 3` — 3 consecutive failures before action
- Readiness and liveness use the same endpoint but readiness has `successThreshold: 1` (default)

### 4. Worker health port: 8080, configurable via `HEALTH_PORT` env var

Port 8080 is conventional for health endpoints and unlikely to conflict (the server uses 8000). Exposed in Helm values as `worker.healthPort`.

### 5. Docker Compose healthcheck: use `curl` for server, `python` stdlib for worker

The errand Docker image is Python-based and may not include `curl`. Use `python -c "import urllib.request; urllib.request.urlopen(...)"` as the healthcheck command (same pattern as the litellm service in deploy/docker-compose.yml). For the server, `curl` may work if available, but python urllib is more reliable since it's guaranteed to be present.

## Risks / Trade-offs

- **Worker health thread adds minimal overhead** → Mitigated by using stdlib `http.server` (no dependencies) and a daemon thread (dies with main process)
- **Health endpoint only checks shutdown flag, not DB** → Acceptable for liveness; the worker's actual DB connectivity is validated per-task. Adding a DB check to the worker health endpoint would require async DB access from a sync thread, adding complexity for marginal benefit.
- **Same endpoint for liveness and readiness** → Acceptable for this application. If we later need different semantics (e.g., readiness should also check Valkey), we can split endpoints.
