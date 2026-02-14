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

## Twitter/X Integration (Optional)

The task runner agent can post tweets via the `post_tweet` MCP tool. To enable this, you need a Twitter/X developer account and API credentials.

### Setting up the X Developer Portal

1. Go to the [X Developer Portal](https://developer.x.com/en/portal/dashboard) and sign in
2. Create a new **Project** and an **App** within it
3. On the app settings page, configure:
   - **App permissions**: Set to **Read and Write** (default is Read-only — posting requires Write)
   - **Type of App**: Select **Web App, Automated App or Bot**
   - **App info**: Fill in the required fields (name, description, website URL)
4. Navigate to **Keys and tokens** and generate:
   - **API Key and Secret** (under Consumer Keys)
   - **Access Token and Secret** (under Authentication Tokens — generate with Read and Write permissions)

### Configuring credentials

Add the following to your `.env` file for local development:

```
TWITTER_API_KEY=your-api-key
TWITTER_API_SECRET=your-api-secret
TWITTER_ACCESS_TOKEN=your-access-token
TWITTER_ACCESS_SECRET=your-access-token-secret
```

For Kubernetes deployment, create a secret with keys matching the env var names above (`TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`) and reference it via `twitter.existingSecret` in your Helm values. The secret is injected using `envFrom`.

## Project Structure

```
backend/          # FastAPI app, SQLAlchemy models, Alembic migrations, worker
frontend/         # Vue 3 SPA (Vite + Tailwind CSS)
helm/             # Helm chart for Kubernetes deployment
openspec/         # Structured change management (spec-driven workflow)
.github/          # CI: build images + Helm chart, push to GHCR
```
