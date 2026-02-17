# Content Manager

A Kanban-style task management application with AI-powered task execution, platform integrations, and a structured content workflow.

## Features

- **5-column Kanban board**: Review, Scheduled, Pending, Running, Completed
- **Drag-and-drop**: Move tasks between columns by dragging cards
- **Task categories**: Immediate, Scheduled, and Repeating tasks
- **AI task runner**: Autonomous agent executes tasks using MCP tools, with real-time log streaming
- **Platform integrations**: Pluggable platform abstraction with encrypted credential storage (Twitter/X supported)
- **Real-time updates**: WebSocket-driven board updates
- **SSO authentication**: Keycloak OIDC with role-based access control (admin/user roles)
- **Audit metadata**: Tasks track created_by/updated_by from authenticated user

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3, Vite, Tailwind CSS, Pinia |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Worker | Python (shared codebase with backend), Docker-in-Docker task runner |
| Database | PostgreSQL |
| Cache | Valkey (Redis-compatible) |
| Auth | Keycloak OIDC (Authorization Code flow) |
| Deployment | Helm on Kubernetes, ArgoCD |
| CI/CD | GitHub Actions |

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│   Frontend   │────▶│   Backend    │────▶│  PostgreSQL   │
│  (Vue 3 SPA) │     │  (FastAPI)   │     └───────────────┘
└──────────────┘     │              │     ┌───────────────┐
                     │  MCP Server  │────▶│    Valkey     │
                     └───────┬──────┘     └───────────────┘
                             │
                      ┌──────▼──────┐     ┌─────────────────┐
                      │   Worker    │────▶│  Task Runner    │
                      │  (polling)  │     │ (DinD container)│
                      └─────────────┘     └─────────────────┘
```

- **Frontend**: Vue 3 SPA served by nginx, communicates with backend via REST API and WebSocket
- **Backend**: FastAPI app handling API endpoints, authentication, and an MCP server for agent tools
- **Worker**: Polls for pending tasks, orchestrates AI agent execution using the MCP SDK
- **Task Runner**: Sandboxed Docker container for executing agent-generated commands
- **Platforms**: Pluggable abstraction layer for external services (Twitter/X, with more planned)

## Local Development

Requires Docker and Docker Compose.

```bash
# Start all services (postgres, migrations, backend, worker, frontend, valkey)
docker compose up --build

# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/api

# Stop and remove containers
docker compose down
```

### Environment Variables

Create a `.env` file with the required configuration:

```bash
# Authentication (required)
OIDC_DISCOVERY_URL=https://your-keycloak/realms/your-realm/.well-known/openid-configuration
OIDC_CLIENT_ID=content-manager
OIDC_CLIENT_SECRET=your-secret

# Credential encryption (required for platform integrations)
CREDENTIAL_ENCRYPTION_KEY=your-fernet-key

# LLM (required for AI task runner)
OPENAI_BASE_URL=https://your-llm-endpoint
OPENAI_API_KEY=your-api-key
```

### Generating a Credential Encryption Key

Platform credentials (e.g. Twitter API keys) are encrypted at rest using [Fernet symmetric encryption](https://cryptography.io/en/latest/fernet/). You must provide a stable `CREDENTIAL_ENCRYPTION_KEY` — without it, platform credential storage is disabled.

Generate a key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the generated key in your `.env` file or Kubernetes secret. The same key must be used across restarts and all replicas — losing the key means stored credentials become unrecoverable.

For Kubernetes deployment, create a secret and reference it via `credentialEncryption.existingSecret` in your Helm values:

```bash
kubectl create secret generic content-manager-credential-key \
  --from-literal=encryption-key="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  -n content-manager
```

## Twitter/X Integration

The platform system supports Twitter/X for posting content. Credentials can be configured via the Settings UI or environment variables.

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

**Option A: Via the Settings UI (recommended)**

Navigate to Settings > Platforms in the web UI, enter your Twitter API credentials, and save. Credentials are encrypted and stored in the database. The UI verifies credentials against the Twitter API before saving.

**Option B: Via environment variables (fallback)**

Add the following to your `.env` file:

```bash
TWITTER_API_KEY=your-api-key
TWITTER_API_SECRET=your-api-secret
TWITTER_ACCESS_TOKEN=your-access-token
TWITTER_ACCESS_SECRET=your-access-token-secret
```

For Kubernetes, create a secret with keys matching the env var names above and reference it via `twitter.existingSecret` in your Helm values. The secret is injected using `envFrom`.

Database-stored credentials take precedence over environment variables.

## Project Structure

```
backend/          # FastAPI app, SQLAlchemy models, Alembic migrations, worker
  platforms/      # Platform abstraction layer (base, twitter, credentials)
  alembic/        # Database migration scripts
frontend/         # Vue 3 SPA (Vite + Tailwind CSS)
  src/components/ # Vue components (Kanban board, settings, modals)
  src/composables/# API client and shared logic
helm/             # Helm chart for Kubernetes deployment
openspec/         # Structured change management (spec-driven workflow)
.github/          # CI: test, build images + Helm chart, push to GHCR
```

## Testing

```bash
# Backend tests (415 tests)
DATABASE_URL="sqlite+aiosqlite:///:memory:" PYTHONPATH=backend \
  backend/.venv/bin/python -m pytest backend/tests/ -v

# Frontend tests (329 tests)
cd frontend && npm test
```
