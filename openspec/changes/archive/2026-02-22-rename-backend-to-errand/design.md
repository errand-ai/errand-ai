## Context

The project has a single combined Docker image (Python app serving both API and frontend static files) but the source directory is still called `backend/`. The CI pipeline builds an image named `errand-backend`, the Helm chart uses `backend:` as the top-level values key, and docker-compose names the service `backend`. The worker uses `BACKEND_MCP_URL` to communicate with the main app. All of these names are vestiges of the original two-container architecture.

## Goals / Non-Goals

**Goals:**
- Rename source directory `backend/` → `errand/` to match the project name
- Rename Docker image from `errand-backend` to `errand`
- Rename Helm values key from `backend:` to `server:` and rename template files
- Rename docker-compose service and env vars to remove "backend" terminology
- Update all specs, CLAUDE.md, and Serena config to reflect new paths
- Ensure ArgoCD external values files continue to work

**Non-Goals:**
- Changing any application logic or behavior
- Renaming the `frontend/` source directory (it's still a separate build stage)
- Cleaning up old `errand-backend` images from GHCR
- Renaming the Alembic migration directory or changing migration history

## Decisions

### 1. Source directory: `backend/` → `errand/`

A simple `git mv backend errand`. All Python imports are relative (no `backend.` package prefix), so internal imports don't change. The Dockerfile, CI pipeline, and CLAUDE.md all reference the directory by path and must be updated.

**Alternative considered**: Renaming to `server/` or `app/`. Rejected because `errand/` directly matches the project name and Docker image name, reducing cognitive overhead.

### 2. Docker image: `errand-backend` → `errand`

The combined image becomes `ghcr.io/errand-ai/errand:<version>`. This is cleaner — the image IS the errand app.

**Alternative considered**: Keeping `errand-backend` to distinguish from the task-runner. Rejected because "errand" vs "errand-task-runner" is already clear without the `-backend` suffix.

### 3. Helm values key: `backend:` → `server:`

The top-level values key changes to `server:`. Template files rename from `backend-deployment.yaml` → `server-deployment.yaml` and `backend-service.yaml` → `server-service.yaml`. The K8s component label changes from `app.kubernetes.io/component: backend` to `app.kubernetes.io/component: server`.

**Alternative considered**: `app:` (generic Helm convention) or `errand:` (matches image). Chose `server:` because it clearly distinguishes from the `worker:` key while describing the component's role. `errand:` would be redundant (the chart is already named errand).

### 4. Env var: `BACKEND_MCP_URL` → `ERRAND_MCP_URL`

Used by the worker to locate the MCP server endpoint. Updated in the Helm worker deployment template, docker-compose, worker source code, and tests.

### 5. Docker Compose service: `backend` → `errand`

The service name changes, which also changes the DNS hostname within the compose network. The worker's `ERRAND_MCP_URL` updates from `http://backend:8000/mcp` to `http://errand:8000/mcp`.

### 6. K8s service name: `errand-backend` → `errand`

The Helm template generates the service name as `{{ include "errand.fullname" . }}-server` which produces `errand-server` with the default release name, or simply by dropping the `-backend` suffix from the template and using `{{ include "errand.fullname" . }}` directly, which produces `errand`. Using `errand` (no suffix) is cleaner since this is the primary service. The ingress and worker templates reference this service name and must be updated.

**Risk**: ArgoCD will see the old `errand-backend` service deleted and a new `errand` service created. With automated sync + prune, this happens atomically. Brief DNS change during sync — acceptable.

## Risks / Trade-offs

- **K8s service rename causes brief disruption** → ArgoCD sync is atomic within a single reconciliation loop. The ingress update happens in the same sync, so new connections route correctly. Existing TCP connections may break during the transition window (seconds).
- **CI immutable tag check references old image name** → Must update the check in the same commit. If the pipeline runs with mixed state (new code, old image name), it will fail-safe (check wrong image, pass, then push to new name).
- **External ArgoCD values file** → The `errand-rancher-values.yaml` does not currently set `backend:` values (it only sets `database:`, `worker:`, `ingress:`, etc.), so no update is needed there. If it did reference `backend:`, it would need to change to `server:`.
