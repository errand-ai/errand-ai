# Healthcheck Probes Implementation (2026-03-12)

## What was done
- Added HTTP health endpoint to worker process (stdlib `http.server` daemon thread on `HEALTH_PORT`, default 8080)
- Wired server `/api/health` and worker `/health` into K8s liveness/readiness probes in Helm templates
- Added Docker Compose healthchecks for server and worker in both testing/ and deploy/ configs
- PR #82, version bumped to 0.77.0

## Key learnings

### Worker health server must start early
The health server MUST start before `pre_pull_images()` in `run()`. The Playwright image pull can take minutes, and if the health endpoint isn't available during that time, Docker Compose and K8s will report the worker as unhealthy. Initial implementation had it after pre-pull — moved it to right after container runtime init.

### Worker health approach: stdlib http.server in daemon thread
The worker is a single-threaded asyncio process (not a web server). A lightweight `http.server.HTTPServer` in a daemon thread is the right approach — no need for FastAPI/uvicorn. The daemon thread dies automatically when the main process exits.

### Health endpoint checks shutdown_requested flag only
The worker health endpoint returns 200 when running, 503 when `shutdown_requested` is True. It does NOT check DB connectivity — that would require async DB access from a sync thread. DB connectivity is validated per-task in the main loop.

### Docker Compose healthcheck command pattern
Use `python -c "import urllib.request; urllib.request.urlopen('http://localhost:PORT/path')"` for healthchecks in Python-based containers — curl may not be available. Same pattern used by litellm service.

### NPM_TOKEN for local builds
`docker compose up --build` needs `NPM_TOKEN` for private `@errand-ai/ui-components` package. Generate it with `NPM_TOKEN=$(gh auth token) docker compose ...`

### Port 5432 conflicts
Check for SSH tunnels or other processes on port 5432 before starting docker-compose (`lsof -i :5432`).

### Colima Docker runtime
Docker runs via Colima on macOS. If docker commands fail with "Cannot connect to Docker daemon", restart Colima with `colima stop && colima start`.
