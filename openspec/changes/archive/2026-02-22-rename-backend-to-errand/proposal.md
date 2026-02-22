## Why

The project originally had separate frontend and backend containers — the `backend/` directory name reflected that split. Since the frontend is now built into the same Docker image and served by the Python app, the "backend" label is misleading. Renaming to `errand/` aligns the source directory, Docker image, Helm templates, and CI pipeline with the project's actual name and single-container architecture.

## What Changes

- Rename source directory `backend/` → `errand/`
- Rename Docker image from `errand-backend` to `errand`
- Rename Helm values key from `backend:` to `server:` and template files from `backend-*` to `server-*`
- Rename docker-compose service from `backend` to `errand`
- Rename `BACKEND_MCP_URL` env var to `ERRAND_MCP_URL` throughout (worker, Helm chart, docker-compose, tests)
- Update K8s component labels from `backend` to `server`
- Update K8s service name from `errand-backend` to `errand`
- Update CI pipeline job names and paths (`build-backend` → `build-errand`, `working-directory: backend` → `errand`)
- Update Dockerfile `COPY backend/` → `COPY errand/`
- Update all test fixtures and spec references from `errand-backend` to `errand`

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `ci-pipelines`: Image name changes from `errand-backend` to `errand`, build job renamed, test working directory changes from `backend` to `errand`
- `helm-deployment`: Values key `backend:` → `server:`, template files renamed, service name changes from `errand-backend` to `errand`, component label changes from `backend` to `server`
- `local-dev-environment`: Docker Compose service renamed from `backend` to `errand`, `BACKEND_MCP_URL` → `ERRAND_MCP_URL`
- `static-file-serving`: Dockerfile references change from `backend/` to `errand/`
- `task-worker`: `BACKEND_MCP_URL` env var renamed to `ERRAND_MCP_URL`
- `backend-tests`: Test directory changes from `backend/tests` to `errand/tests`, test working directory in CI changes

## Impact

- **Source tree**: `backend/` directory renamed to `errand/`, including all Python source, tests, Alembic migrations, requirements files, and `.venv`
- **Docker images**: Registry image name changes — old `errand-backend:*` images remain in GHCR but are no longer produced
- **Kubernetes**: Service name change from `errand-backend` to `errand` means ArgoCD will delete the old service and create a new one (brief disruption during sync)
- **ArgoCD override values**: External `errand-rancher-values.yaml` in the argocd repo must be updated to use `server:` key instead of `backend:` (if it references `backend:` — currently it does not, so no change needed there)
- **CLAUDE.md**: All references to `backend/` paths and `backend/.venv` need updating
- **Serena config**: `.serena/project.yml` references to `backend/` need updating
- **OpenSpec specs**: 6 specs contain references to `backend` that need updating in delta specs
