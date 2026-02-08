## 1. Project Structure and Configuration

- [ ] 1.1 Create `VERSION` file at repo root with initial version `0.1.0`
- [ ] 1.2 Create backend Python package structure: `backend/` with `__init__.py`, `main.py`, `models.py`, `database.py`, `worker.py`, `requirements.txt`
- [ ] 1.3 Create frontend project structure: `frontend/` with Vite + Vue 3 + Tailwind CSS scaffolding (`package.json`, `vite.config.ts`, `tailwind.config.js`, `src/`)
- [ ] 1.4 Create `backend/alembic.ini` and `backend/alembic/` directory with Alembic configuration pointing to `DATABASE_URL` env var

## 2. Database Models and Migrations

- [ ] 2.1 Implement `backend/database.py` with SQLAlchemy async engine and session factory reading `DATABASE_URL` from environment
- [ ] 2.2 Implement `backend/models.py` with `Task` model: `id` (UUID PK), `title` (text not null), `status` (text not null, default `pending`), `created_at` (timestamptz), `updated_at` (timestamptz)
- [ ] 2.3 Create initial Alembic migration that generates the `tasks` table from the SQLAlchemy model

## 3. Backend API

- [ ] 3.1 Implement `backend/main.py` with FastAPI app, CORS middleware, and lifespan handler for database connection
- [ ] 3.2 Implement `GET /api/tasks` endpoint returning all tasks ordered by creation time descending
- [ ] 3.3 Implement `POST /api/tasks` endpoint accepting `{"title": "..."}`, creating a task with status `pending`, returning 201
- [ ] 3.4 Implement `GET /api/tasks/{id}` endpoint returning a single task or 404
- [ ] 3.5 Implement `GET /api/metrics/queue` endpoint returning `{"queue_depth": N}` where N is the count of pending tasks
- [ ] 3.6 Implement `GET /api/health` endpoint returning 200 when database is reachable, 503 otherwise

## 4. Worker Process

- [ ] 4.1 Implement `backend/worker.py` with a polling loop that uses `SELECT ... FOR UPDATE SKIP LOCKED` to dequeue one pending task
- [ ] 4.2 Implement task processing: set status to `running`, execute task logic (MVP: sleep placeholder), set status to `completed`
- [ ] 4.3 Implement error handling: catch exceptions during processing, set task status to `failed`, log error, continue polling
- [ ] 4.4 Implement graceful shutdown: handle SIGTERM, finish current task before exiting

## 5. Frontend Application

- [ ] 5.1 Initialize Vite + Vue 3 + TypeScript project in `frontend/` with Tailwind CSS configured
- [ ] 5.2 Create Pinia store (`useTaskStore`) with `tasks` state, `fetchTasks` action, and computed getters for tasks grouped by status
- [ ] 5.3 Implement API client module (composable) with functions for `GET /api/tasks` and `POST /api/tasks`
- [ ] 5.4 Implement KanbanBoard component with columns for Pending, Running, Completed, and Failed using `v-for` over status groups
- [ ] 5.5 Implement TaskCard component displaying task title, wrapped in `<TransitionGroup>` for animated column transitions
- [ ] 5.6 Implement task creation form with title input and validation (reject empty titles)
- [ ] 5.7 Implement polling in the Pinia store to refresh task state at a regular interval
- [ ] 5.8 Create nginx configuration: serve static assets, proxy `/api/*` to the backend service

## 6. Docker Images

- [ ] 6.1 Create `frontend/Dockerfile`: multi-stage with Node build stage and nginx runtime stage
- [ ] 6.2 Create `backend/Dockerfile`: multi-stage with Python build stage and slim runtime stage, default entrypoint for the API server
- [ ] 6.3 Add `.dockerignore` files for frontend and backend to exclude unnecessary files
- [ ] 6.4 Verify both images build locally with `docker build`

## 7. Helm Chart

- [ ] 7.1 Create Helm chart structure at `helm/content-manager/` with `Chart.yaml`, `values.yaml`, and `templates/`
- [ ] 7.2 Create frontend Deployment and Service templates
- [ ] 7.3 Create backend Deployment and Service templates with `DATABASE_URL` from existing Secret reference
- [ ] 7.4 Create worker Deployment template (replicaCount 0, same image as backend with worker entrypoint)
- [ ] 7.5 Create KEDA ScaledObject template targeting worker Deployment with HTTP trigger polling `GET /api/metrics/queue`
- [ ] 7.6 Create database migration Job template as Helm pre-upgrade hook using backend image with `alembic upgrade head` entrypoint
- [ ] 7.7 Create Ingress template with configurable host and TLS settings
- [ ] 7.8 Configure `values.yaml` with sensible defaults: image repo/tag, replicaCounts, KEDA settings, ingress host, database secret name

## 8. Local Development Environment

- [ ] 8.1 Create `docker-compose.yml` at repo root with services: postgres, migrate, backend, worker, frontend
- [ ] 8.2 Configure postgres service with health check, preconfigured database name, and exposed port `5432`
- [ ] 8.3 Configure migrate service using backend image with `alembic upgrade head` entrypoint, depends on postgres health
- [ ] 8.4 Configure backend service with `DATABASE_URL` pointing to postgres, exposed on port `8000`, depends on migrate
- [ ] 8.5 Configure worker service using backend image with worker entrypoint, depends on migrate
- [ ] 8.6 Configure frontend service building from `frontend/Dockerfile`, exposed on port `3000`, proxying `/api/*` to backend
- [ ] 8.7 Verify full stack starts with `docker compose up` and tasks can be created and processed end-to-end

## 9. CI/CD Pipelines

- [ ] 9.1 Create `.github/workflows/build.yml` triggered on push to `main` and pull request
- [ ] 9.2 Implement version reading step: read `VERSION` file, append `-pr<number>` for PR builds
- [ ] 9.3 Implement Docker build and push steps for frontend and backend images using the computed tag
- [ ] 9.4 Implement Helm chart packaging step: set `version` and `appVersion` from `VERSION`, package chart
- [ ] 9.5 Implement Helm chart push step (main branch only) to chart registry
- [ ] 9.6 Implement immutable version check on main: fail if the image tag already exists in the container registry
