## Context

The application currently deploys as two containers: a Python/FastAPI backend (uvicorn) and a Vue 3 frontend (nginx serving static files). In Kubernetes, the ingress routes `/api`, `/auth`, `/mcp`, `/slack` to the backend service and `/` to the frontend service. In docker-compose, the frontend nginx proxies API/auth requests to the backend and serves static files for everything else.

This separation adds operational overhead (two images, two deployments, two services, nginx config maintenance) with no benefit at our scale. The frontend is a static SPA with no server-side rendering.

## Goals / Non-Goals

**Goals:**
- Serve frontend static files directly from FastAPI, eliminating the nginx container
- Single Docker image and Kubernetes deployment for the web-facing application
- Simplified ingress (all paths to one service), CI pipeline (one fewer image), and docker-compose config
- Preserve the Vite HMR dev workflow (frontend development unchanged)

**Non-Goals:**
- CDN or edge caching for static assets (can be added later if needed)
- Server-side rendering
- Changing the worker deployment (stays separate)
- Changing the task-runner image build (stays separate)

## Decisions

### Decision 1: Use Starlette StaticFiles + catch-all FileResponse

**Choice**: Mount `/assets` with `StaticFiles(directory="static/assets")` for hashed Vite output, then add a catch-all route that serves `index.html` for unmatched paths.

**Why**: Vite outputs hashed filenames in `/assets/` (e.g., `index-abc123.js`). These can be served directly by `StaticFiles` which handles etags and content types. The catch-all handles SPA routing (Vue Router history mode) by returning `index.html` for any path not matched by an API route.

**Alternative considered**: Using `StaticFiles(directory="static", html=True)` — this serves `index.html` for directory paths but doesn't do SPA fallback for deep routes like `/tasks/123`.

**Route ordering**: FastAPI matches routes in registration order. All API/auth/MCP routes are registered before the catch-all, so they take priority. The catch-all is a `@app.get("/{path:path}")` at the very end.

### Decision 2: Multi-stage Dockerfile (node + python)

**Choice**: Single `backend/Dockerfile` with three stages:
1. `frontend-build`: node:20-alpine, `npm ci && npm run build`
2. `build`: python:3.12, `pip install`
3. Final: python:3.12-slim, copies Python packages + frontend `dist/` → `/app/static/`

**Why**: Keeps a single image with minimal size. The node stage is only used during build and doesn't bloat the final image. The frontend source moves into the backend build context via a COPY from the repo root.

**Build context change**: The backend Dockerfile will need the frontend source. Two options:
- (a) Set Docker build context to repo root, adjust COPY paths
- (b) Keep context as `./backend`, copy `frontend/dist` into backend dir before build

**Choice**: Option (a) — set build context to repo root. Cleaner, no pre-copy step, works naturally in both CI and docker-compose. The Dockerfile paths become `COPY frontend/ /frontend/` and `COPY backend/ /app/`.

### Decision 3: Static files only in production mode

**Choice**: Only mount the static file routes if the `static/` directory exists. In development, the Vite dev server handles the frontend separately — the backend doesn't need to serve static files.

**Why**: During local development with `docker compose up`, the backend volume-mounts `./backend:/app` which won't have a `static/` directory. The frontend is served by Vite's dev server or the docker-compose frontend service. The static mount only activates in the production Docker image where `static/` is baked in.

### Decision 4: Serve additional static files (favicon, etc.)

**Choice**: Mount the `static/` directory root for specific known files (`favicon.ico`, `robots.txt`, etc.) and the `/assets/` subdirectory for Vite's hashed output. The catch-all route handles everything else as SPA routing.

**Why**: Vite puts hashed JS/CSS in `assets/` but also copies files from `public/` to the dist root (favicon, manifest, etc.). These need to be served at their exact paths.

**Implementation**: Try to serve the file from `static/` first; if it doesn't exist, fall back to `index.html`.

## Risks / Trade-offs

**[Static file performance]** → Uvicorn/Python serving static files is slower than nginx. At our scale (single users, not a public SaaS), this is irrelevant. If needed later, a CDN or nginx reverse proxy can be added in front.

**[Build context size]** → Setting build context to repo root means Docker sends more files. Mitigated with a `.dockerignore` that excludes `node_modules/`, `.git/`, `openspec/`, etc.

**[Catch-all route conflicts]** → The `/{path:path}` catch-all could mask 404s for API routes. Mitigated by registering it last and ensuring all API routes use explicit path prefixes (`/api/`, `/auth/`, etc.).

**[Rollback]** → If the merged deployment has issues, rolling back means re-deploying the last version that had separate images. The Helm chart change is backwards-incompatible (removes frontend templates), so rollback requires the old chart version too. Low risk since the change is straightforward.

## Migration Plan

1. Bump VERSION
2. Modify backend to conditionally serve static files
3. Create new multi-stage Dockerfile at repo root (or modify backend/Dockerfile)
4. Update docker-compose to remove frontend service
5. Update Helm chart: remove frontend templates, simplify ingress
6. Update CI: remove build-frontend job, adjust build-backend context
7. Delete frontend/Dockerfile and frontend/nginx.conf
8. Test locally with `docker compose up`
9. Push, verify CI, verify K8s deployment

## Open Questions

None — the approach is well-understood from the exploration discussion.
