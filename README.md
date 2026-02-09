# Content Manager

A Kanban-style task management application for tracking content through a multi-stage workflow.

## Features

- **7-column Kanban board**: New, Need Input, Scheduled, Pending, Running, Review, Completed
- **Drag-and-drop**: Move tasks between columns by dragging cards
- **Inline editing**: Edit task title and status via a modal dialog
- **Real-time polling**: Board auto-refreshes to reflect changes
- **SSO authentication**: Keycloak OIDC with role-based access control

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3, Vite, Tailwind CSS, Pinia |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Worker | Python (shared codebase with backend) |
| Database | PostgreSQL |
| Auth | Keycloak OIDC (Authorization Code flow) |
| Deployment | Helm on Kubernetes, ArgoCD, KEDA |
| CI/CD | GitHub Actions |

## Local Development

Requires Docker and Docker Compose.

```bash
# Start all services (postgres, migrations, backend, worker, frontend)
docker compose up --build

# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/api

# Stop and remove containers
docker compose down
```

OIDC environment variables are required for authentication. Create a `.env` file:

```
OIDC_DISCOVERY_URL=https://your-keycloak/realms/your-realm/.well-known/openid-configuration
OIDC_CLIENT_ID=content-manager
OIDC_CLIENT_SECRET=your-secret
```

## Project Structure

```
backend/          # FastAPI app, SQLAlchemy models, Alembic migrations, worker
frontend/         # Vue 3 SPA (Vite + Tailwind CSS)
helm/             # Helm chart for Kubernetes deployment
openspec/         # Structured change management (spec-driven workflow)
.github/          # CI: build images + Helm chart, push to GHCR
```
