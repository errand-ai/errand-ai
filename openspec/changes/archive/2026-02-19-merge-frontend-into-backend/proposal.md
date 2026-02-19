## Why

The frontend and backend are deployed as separate containers — the frontend is an nginx image serving static files, the backend is a uvicorn/FastAPI service. This means two Docker images to build, two Kubernetes deployments to manage, an nginx config to maintain, and ingress path-routing split across two services. Merging them into a single service simplifies deployment, CI, and the Helm chart with no meaningful downside at our scale.

## What Changes

- **Backend serves frontend static files**: FastAPI serves the Vite build output (`dist/`) for all non-API routes, replacing nginx
- **SPA fallback route**: A catch-all route serves `index.html` for any path not matched by API/auth/MCP routes (replaces nginx `try_files`)
- **Combined Docker image**: Single multi-stage Dockerfile — node stage builds frontend, Python stage runs everything
- **BREAKING: Frontend container removed**: No more separate frontend deployment, service, or image
- **Helm chart simplified**: Frontend deployment, service, and configmap templates removed; ingress routes everything to the backend
- **CI simplified**: One fewer image to build and push; frontend build becomes a stage in the backend image build
- **docker-compose simplified**: Frontend service removed; backend serves static files directly on port 8000

## Capabilities

### New Capabilities
- `static-file-serving`: Backend serves frontend static assets and provides SPA fallback routing

### Modified Capabilities
- `helm-deployment`: Frontend deployment/service/configmap removed; ingress routes all paths to backend
- `ci-pipelines`: Frontend image build removed; backend Dockerfile gains a node build stage; one fewer build job
- `local-dev-environment`: Frontend docker-compose service removed; backend serves static files; dev workflow with Vite HMR unchanged

## Impact

- **Backend**: New static file mount and catch-all route added to FastAPI app
- **Dockerfile**: `backend/Dockerfile` becomes a multi-stage build (node + Python); `frontend/Dockerfile` deleted
- **Helm chart**: 3 templates removed (`frontend-deployment.yaml`, `frontend-service.yaml`, `frontend-configmap.yaml`), ingress simplified
- **CI**: `build-frontend` job removed from GitHub Actions workflow; `build-backend` job builds the combined image
- **docker-compose**: `frontend` service removed; port 3000 no longer used (backend on 8000 serves everything)
- **Frontend dev**: No change — `npm run dev` with Vite HMR still works independently for development
- **nginx.conf**: Deleted (no longer needed)
