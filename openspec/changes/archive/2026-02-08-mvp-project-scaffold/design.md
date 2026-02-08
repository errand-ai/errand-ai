## Context

This is a greenfield project. There is no existing codebase — we are establishing the foundational architecture for a Kanban-style task processing application. The system has three runtime components (frontend, backend, worker) deployed to Kubernetes, with PostgreSQL as the sole persistent store. The database is provisioned externally; the application owns its schema via migrations.

ArgoCD manages deployments from a Helm chart stored alongside application code. KEDA scales worker pods based on queue depth exposed by the backend.

## Goals / Non-Goals

**Goals:**

- Establish a working project structure with all three components buildable and deployable
- Create a minimal but functional Kanban UI that can display and move tasks between columns
- Backend serves a REST API for task operations and exposes a metrics endpoint for KEDA
- Worker process pulls and executes one task at a time from the backend-managed queue
- Database migrations run automatically before application startup
- Helm chart deploys all components with KEDA ScaledObject for worker autoscaling
- GitHub Actions build Docker images and Helm chart on push to main and PR creation
- Immutable versioning: tags derived from a single source of truth version, PR builds append `-pr<number>`
- Docker Compose environment for local development and testing — all changes must be tested locally before pushing

**Non-Goals:**

- Authentication, authorization, or multi-tenancy
- Production-grade observability (metrics, tracing, structured logging beyond basics)
- Complex task scheduling, priorities, or dependencies between tasks
- Horizontal pod autoscaling for the backend (manual replica count is sufficient for MVP)
- Frontend SSR or SEO optimization
- Database provisioning or backup/restore tooling
- ArgoCD Application manifests (ArgoCD configuration is external to this repo)

## Decisions

### Frontend: Vite + Vue 3 + Tailwind CSS

Vue 3 with Vite for fast builds and HMR. Tailwind CSS for utility-first styling without a component library dependency. The frontend is built as static assets served by nginx in its own container.

Vue 3's Composition API with `<script setup>` provides explicit reactivity via `ref()` and `reactive()` without the stale closure pitfalls of React hooks. Pinia provides first-party state management, eliminating the need to choose between competing React state libraries. Vue's built-in `<TransitionGroup>` component handles card animation between Kanban columns natively — a core UX need that React requires third-party libraries to achieve. Single-file components (`.vue` with template/script/style) keep each component self-contained and readable.

**Alternatives considered:** React + Vite (larger ecosystem but no built-in transitions, state library selection overhead, larger runtime at ~42KB vs Vue's ~16KB gzipped), Next.js (unnecessary SSR complexity for a SPA), serving static files from the backend (couples deployment lifecycles).

### Backend: FastAPI + SQLAlchemy + Alembic

FastAPI for async REST endpoints with automatic OpenAPI docs. SQLAlchemy as the ORM with Alembic for migrations. The backend is stateless — all state lives in PostgreSQL.

**Alternatives considered:** Flask (lacks async, no built-in OpenAPI), Django (heavier than needed for an API-only service).

### Task queue: Database-backed queue via PostgreSQL

Tasks are stored in a `tasks` table with a `status` column. Workers poll for tasks with status `pending` using `SELECT ... FOR UPDATE SKIP LOCKED` to safely dequeue without contention. This avoids introducing a separate message broker for the MVP.

**Alternatives considered:** Redis queue (extra infrastructure dependency), RabbitMQ (overkill for MVP). The database-backed approach is simple, transactional, and sufficient for initial scale. Can migrate to a dedicated broker later if needed.

### Worker: Same Python codebase as backend, separate entrypoint

The worker shares the backend's Python package (models, database connection) but has its own entrypoint that runs a polling loop. This keeps the codebase DRY and avoids model/schema drift between backend and worker.

**Alternatives considered:** Separate Python package (code duplication), Celery (heavy dependency for a simple polling worker).

### Database migrations: Alembic run as a Kubernetes Job

Migrations run as a Helm pre-upgrade hook Job before the backend or worker pods start. This ensures the schema is current before any application code runs. The Job uses the same backend Docker image with `alembic upgrade head` as the entrypoint.

**Alternatives considered:** Init container on backend pods (runs on every pod restart, race conditions with multiple replicas), manual migration step (error-prone).

### Container images: Multi-stage Dockerfiles

- **Frontend**: Node build stage → nginx runtime stage
- **Backend/Worker**: Python build stage (install deps) → slim runtime stage

Backend and worker share a single Docker image with different entrypoint commands to avoid building two nearly-identical images.

### Versioning: Single source of truth in `VERSION` file

A `VERSION` file at the repo root contains the semver version (e.g. `0.1.0`). GitHub Actions reads this file:
- **On main**: tags images and Helm chart as `0.1.0`
- **On PR**: tags as `0.1.0-pr<number>`

This keeps versioning simple and auditable. Developers bump the `VERSION` file as part of their changes.

### Helm chart structure

A single chart in `helm/content-manager/` with subcomponents:
- Frontend Deployment + Service
- Backend Deployment + Service
- Worker Deployment (replica count 0 — KEDA manages scaling)
- KEDA ScaledObject targeting the worker Deployment, using an HTTP-based trigger pointing at the backend's metrics endpoint
- Migration Job as a pre-upgrade hook
- Ingress resource for external access

### KEDA metrics endpoint

The backend exposes `GET /api/metrics/queue` returning `{"queue_depth": N}` where N is the count of tasks with status `pending`. KEDA uses an HTTP-scaled trigger polling this endpoint. When queue_depth > 0, KEDA scales workers up (one task per worker pod). When queue_depth returns to 0, KEDA scales workers back to 0.

### Local development: Docker Compose

A `docker-compose.yml` at the repo root runs the full stack locally for fast feedback and testing before committing changes:
- **postgres**: PostgreSQL container with a preconfigured database, exposed on `localhost:5432`
- **migrate**: Runs `alembic upgrade head` against the local PostgreSQL, exits on completion (depends on postgres)
- **backend**: FastAPI backend with `DATABASE_URL` pointing to the local PostgreSQL, exposed on `localhost:8000`
- **worker**: Worker process using the same backend image with worker entrypoint (depends on migrate)
- **frontend**: Nginx-served frontend with `/api/*` proxied to the backend container, exposed on `localhost:3000`

The backend and worker services mount the local `backend/` source directory for live reloading during development. The frontend service builds from the Dockerfile for production-like testing.

All changes MUST be tested locally using `docker compose up` before committing and pushing to trigger CI pipelines.

**Alternatives considered:** Running services natively without containers (inconsistent environments, manual PostgreSQL setup), using Tilt or Skaffold with a local K8s cluster (overkill for MVP development).

### CI/CD: GitHub Actions

Two workflow triggers:
- **Push to main**: Build images, push to container registry, package Helm chart, push to chart registry
- **Pull request**: Same build steps but with `-pr<number>` tag suffix, no chart registry push (images only for testing)

Both workflows read `VERSION` for the base tag. The PR workflow appends the PR number.

## Risks / Trade-offs

- **Database-as-queue scalability**: `SELECT FOR UPDATE SKIP LOCKED` works well at moderate scale but may become a bottleneck under high task throughput → Mitigation: monitor query latency; design the worker interface so swapping to a dedicated broker later is a single-module change
- **Single Docker image for backend and worker**: Couples their release cycles — a backend-only change forces a worker redeploy → Mitigation: acceptable for MVP; split images later if deployment frequency diverges
- **KEDA HTTP trigger latency**: KEDA polls the metrics endpoint on an interval (default 30s), so there's a delay between task creation and worker scale-up → Mitigation: configure a shorter polling interval (e.g. 10s); pre-warm with `minReplicaCount: 1` if latency is unacceptable
- **Migration Job failure**: If the migration Job fails, the Helm release is blocked → Mitigation: Helm hook rollback policy; migrations must be backward-compatible (additive only)
- **VERSION file conflicts**: Multiple PRs may try to bump the same version → Mitigation: CI checks that the version in `VERSION` on main hasn't already been published; merge conflicts force resolution
