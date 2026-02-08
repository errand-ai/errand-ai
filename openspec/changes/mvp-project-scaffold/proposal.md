## Why

This project needs a foundational structure before any features can be built. We need a frontend/backend/worker architecture with CI/CD pipelines, container builds, and Kubernetes deployment manifests — all wired together so that subsequent changes can focus on application logic rather than infrastructure plumbing.

## What Changes

- Create a Vue 3 + Tailwind CSS frontend application with a Kanban board view for task management
- Create a Python backend API (FastAPI) that manages tasks, serves the frontend, and exposes task queue metrics for KEDA autoscaling
- Create a Python worker process that pulls tasks from a queue maintained by the backend, processing one task at a time
- Set up PostgreSQL database migrations (Alembic) managed by the application, with the database itself deployed externally
- Create Dockerfiles for frontend, backend, and worker images
- Create a Helm chart for Kubernetes deployment including KEDA ScaledObject configuration for worker autoscaling
- Set up GitHub Actions pipelines for building images and packaging the Helm chart on push to main and PR creation
- Implement immutable versioning: application version is the image/chart tag on main, appended with PR number (e.g. `0.1.0-pr42`) for pull request builds
- Create a Docker Compose environment for local development and testing with all services (frontend, backend, worker, PostgreSQL)

## Capabilities

### New Capabilities

- `kanban-frontend`: Vue 3 + Tailwind CSS single-page application providing a Kanban board UI with task columns, drag-and-drop interaction, and built-in transition animations, communicating with the backend API
- `task-api`: Python FastAPI backend exposing REST endpoints for task CRUD, task state transitions, and a task queue metrics endpoint consumable by KEDA
- `task-worker`: Python worker process that connects to the backend's task queue, pulls pending tasks one at a time, and executes them
- `database-migrations`: Alembic-based schema migration system for PostgreSQL, run as an init container or job before application startup
- `helm-deployment`: Helm chart defining Kubernetes manifests for frontend, backend, worker (with KEDA ScaledObject), database migration job, services, and ingress
- `local-dev-environment`: Docker Compose configuration for running the full application stack locally (frontend, backend, worker, PostgreSQL) for fast feedback and testing before pushing to CI
- `ci-pipelines`: GitHub Actions workflows for building Docker images, packaging the Helm chart, and managing immutable version tags across main and PR builds

### Modified Capabilities

_(none — greenfield project)_

## Impact

- **Repository structure**: Introduces `frontend/`, `backend/`, `worker/`, `helm/`, and `.github/workflows/` directories
- **Dependencies**: Vue 3, Pinia, Tailwind CSS, FastAPI, SQLAlchemy, Alembic, psycopg2
- **Infrastructure**: Requires a Kubernetes cluster with KEDA installed, an external PostgreSQL database, a container registry for images, and ArgoCD for deployment
- **CI/CD**: GitHub Actions will build and push Docker images and Helm charts on every push to main and every PR
