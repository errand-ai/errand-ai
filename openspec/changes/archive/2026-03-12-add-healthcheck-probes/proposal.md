## Why

The errand server has a `/api/health` endpoint but it is not wired into any orchestration layer. The worker has no health mechanism at all. Without liveness and readiness probes, Kubernetes cannot detect hung or crashed containers, and Docker Compose services start without confirming the application is actually ready to serve traffic or process tasks.

## What Changes

- Add a lightweight HTTP health endpoint to the worker process (a background thread serving `/health` on a configurable port)
- Wire the existing server `/api/health` endpoint into Kubernetes liveness and readiness probes in the Helm server deployment
- Add Kubernetes liveness and readiness probes to the Helm worker deployment using the new worker health endpoint
- Add Docker Compose `healthcheck` directives for the errand server and worker services in both `testing/docker-compose.yml` and `deploy/docker-compose.yml`
- Add `condition: service_healthy` to downstream service `depends_on` where the errand server or worker are dependencies

## Capabilities

### New Capabilities

- `healthcheck-probes`: Health check endpoints and orchestration probe configuration for both server and worker containers

### Modified Capabilities

- `helm-deployment`: Add liveness/readiness probe configuration to server and worker deployment templates and values
- `local-dev-environment`: Add healthcheck directives to errand and worker services in docker-compose
- `container-runtime`: Worker process gains a health HTTP thread that reports liveness based on the poll loop running and DB connectivity

## Impact

- **errand/worker.py**: New background HTTP health server thread (minimal — stdlib `http.server` or similar)
- **helm/errand/templates/server-deployment.yaml**: Add livenessProbe and readinessProbe
- **helm/errand/templates/worker-deployment.yaml**: Add livenessProbe and readinessProbe, expose health port
- **helm/errand/values.yaml**: Add probe configuration defaults (paths, ports, intervals)
- **testing/docker-compose.yml**: Add healthcheck to errand and worker services
- **deploy/docker-compose.yml**: Add healthcheck to errand and worker services
- **No breaking changes** — all additions are backwards-compatible
