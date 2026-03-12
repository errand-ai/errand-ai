## 1. Worker Health Endpoint

- [x] 1.1 Add a background HTTP health server to `errand/worker.py` — stdlib `http.server` in a daemon thread, serving `GET /health` on `HEALTH_PORT` (default 8080). Return 200 `{"status": "ok"}` when healthy, 503 `{"status": "shutting_down"}` when `shutdown_requested` is True.
- [x] 1.2 Start the health server thread in `run()` before the main poll loop, after runtime initialisation.
- [x] 1.3 Add tests for the worker health endpoint (200 when healthy, 503 after shutdown signal).

## 2. Helm Deployment Probes

- [x] 2.1 Add `livenessProbe` and `readinessProbe` to `helm/errand/templates/server-deployment.yaml` using httpGet on `/api/health` port 8000 (initialDelaySeconds: 10/5, periodSeconds: 15, timeoutSeconds: 5, failureThreshold: 3).
- [x] 2.2 Add `livenessProbe` and `readinessProbe` to `helm/errand/templates/worker-deployment.yaml` using httpGet on `/health` port `{{ .Values.worker.healthPort }}`. Add `HEALTH_PORT` env var and `containerPort` entry.
- [x] 2.3 Add `worker.healthPort: 8080` default to `helm/errand/values.yaml`.

## 3. Docker Compose Healthchecks

- [x] 3.1 Add `healthcheck` to the errand server service in `testing/docker-compose.yml` — python urllib check against `http://localhost:8000/api/health`, interval 10s, timeout 5s, retries 5.
- [x] 3.2 Add `healthcheck` to the worker service in `testing/docker-compose.yml` — python urllib check against `http://localhost:8080/health`, interval 10s, timeout 5s, retries 5.
- [x] 3.3 Add `healthcheck` to the errand server service in `deploy/docker-compose.yml` — python urllib check against `http://localhost:8000/api/health`, interval 10s, timeout 5s, retries 5.
- [x] 3.4 Add `healthcheck` to the worker service in `deploy/docker-compose.yml` — python urllib check against `http://localhost:8080/health`, interval 10s, timeout 5s, retries 5.
