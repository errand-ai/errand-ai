## 1. Source Directory Rename

- [x] 1.1 Rename `backend/` directory to `errand/` via `git mv backend errand`
- [x] 1.2 Recreate Python venv at `errand/.venv` and install dependencies

## 2. Dockerfile

- [x] 2.1 Update Dockerfile: change `COPY backend/requirements.txt` to `COPY errand/requirements.txt`
- [x] 2.2 Update Dockerfile: change `COPY backend/ .` to `COPY errand/ .`

## 3. Docker Compose

- [x] 3.1 Rename `backend` service to `errand` in `docker-compose.yml`
- [x] 3.2 Update worker `BACKEND_MCP_URL` to `ERRAND_MCP_URL` with value `http://errand:8000/mcp`
- [x] 3.3 Update migrate service to use correct build context (unchanged but verify)

## 4. Worker Source Code

- [x] 4.1 Update `errand/worker.py`: rename `BACKEND_MCP_URL` env var reference to `ERRAND_MCP_URL`
- [x] 4.2 Update all test files referencing `BACKEND_MCP_URL` to `ERRAND_MCP_URL`
- [x] 4.3 Update all test fixtures referencing `errand-backend` hostnames to `errand`

## 5. CI Pipeline

- [x] 5.1 Update `.github/workflows/build.yml`: rename `build-backend` job to `build-errand`
- [x] 5.2 Update CI: change image name from `errand-backend` to `errand` in immutable tag check
- [x] 5.3 Update CI: change image tag from `errand-backend` to `errand` in build-and-push step
- [x] 5.4 Update CI: change test `working-directory` from `backend` to `errand`
- [x] 5.5 Update CI: change `helm` job `needs` from `build-backend` to `build-errand`

## 6. Helm Chart

- [x] 6.1 Rename `helm/errand/values.yaml`: change top-level key from `backend:` to `server:`, update default image repository to `ghcr.io/errand-ai/errand`
- [x] 6.2 Rename template file `backend-deployment.yaml` to `server-deployment.yaml` and update all `backend` references to `server` inside
- [x] 6.3 Rename template file `backend-service.yaml` to `server-service.yaml` and update all `backend` references to `server`, change service name to `{{ include "errand.fullname" . }}`
- [x] 6.4 Update `helm/errand/templates/ingress.yaml`: change service name from `errand-backend` pattern to `{{ include "errand.fullname" . }}`
- [x] 6.5 Update `helm/errand/templates/worker-deployment.yaml`: change `BACKEND_MCP_URL` to `ERRAND_MCP_URL`, update service reference from `backend` to use `{{ include "errand.fullname" . }}`, change `.Values.backend.` to `.Values.server.`
- [x] 6.6 Update `helm/errand/templates/migration-job.yaml`: change `.Values.backend.` to `.Values.server.`
- [x] 6.7 Update `helm/errand/templates/keda-scaledobject.yaml`: change `backend` service reference and `.Values.backend.` to `.Values.server.`

## 7. OpenSpec Specs

- [x] 7.1 Update `openspec/specs/task-worker/spec.md`: replace `BACKEND_MCP_URL` with `ERRAND_MCP_URL` and `errand-backend` with `errand`
- [x] 7.2 Update `openspec/specs/ci-pipelines/spec.md`: replace `backend` references with updated names per delta spec
- [x] 7.3 Update `openspec/specs/helm-deployment/spec.md`: replace `backend` references with `server` per delta spec
- [x] 7.4 Update `openspec/specs/local-dev-environment/spec.md`: replace `backend` service name with `errand` and `BACKEND_MCP_URL` with `ERRAND_MCP_URL`
- [x] 7.5 Update `openspec/specs/static-file-serving/spec.md`: replace `backend/` path references with `errand/`
- [x] 7.6 Update `openspec/specs/backend-tests/spec.md`: replace `backend/` directory references with `errand/`

## 8. Project Configuration

- [x] 8.1 Update `CLAUDE.md`: replace all `backend/` path references with `errand/`, update venv path, update CI job names
- [x] 8.2 Update `.serena/project.yml`: replace `backend/` path references with `errand/`

## 9. Verification

- [x] 9.1 Run application tests: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`
- [x] 9.2 Run frontend tests: `cd frontend && npm test`
- [x] 9.3 Verify `docker compose up --build` starts successfully with renamed service
- [x] 9.4 Verify `helm template` renders correctly with new values structure
