## 1. Backend Static File Serving

- [x] 1.1 Add static file serving to FastAPI app: mount `/assets` with `StaticFiles` and add SPA catch-all route, conditional on `static/` directory existing
- [x] 1.2 Add backend tests for static file serving (asset serving, SPA fallback, API routes unaffected)

## 2. Combined Dockerfile

- [x] 2.1 Create new multi-stage Dockerfile at repo root: node stage builds frontend, python stage copies backend + frontend dist into final image
- [x] 2.2 Add `.dockerignore` at repo root to exclude `node_modules/`, `.git/`, `openspec/`, etc.
- [x] 2.3 Delete `frontend/Dockerfile` and `frontend/nginx.conf`

## 3. Docker Compose

- [x] 3.1 Update `docker-compose.yml`: remove `frontend` service, update backend build context to repo root, update backend Dockerfile path
- [x] 3.2 Verify `docker compose up --build` works end-to-end (backend serves frontend at localhost:8000)

## 4. Helm Chart

- [x] 4.1 Delete `frontend-deployment.yaml`, `frontend-service.yaml`, and `frontend-configmap.yaml` from Helm templates
- [x] 4.2 Simplify `ingress.yaml`: route all paths to backend service only
- [x] 4.3 Remove `frontend` section from `values.yaml` and update `_helpers.tpl` if it references frontend
- [x] 4.4 Update backend Dockerfile path in values if needed (context is now repo root) *(no change needed — values only reference image repo/tag, not Dockerfile)*

## 5. CI Pipeline

- [x] 5.1 Remove `build-frontend` job from `.github/workflows/build.yml`
- [x] 5.2 Update `build-backend` job: set build context to repo root, point to new Dockerfile
- [x] 5.3 Remove frontend image from immutable version tag check
- [x] 5.4 Update `helm` job `needs` to remove `build-frontend` dependency
- [x] 5.5 Verify frontend tests still run in the `test` job (unchanged) *(confirmed — test job still has both backend and frontend test steps)*

## 6. Cleanup and Documentation

- [x] 6.1 Update `CLAUDE.md` to reflect merged architecture (port 8000 serves everything, no frontend container)
- [x] 6.2 Bump `VERSION` file
