# Content Manager

A Kanban-style task management application with AI-powered task execution, platform integrations, and a structured content workflow.

## Features

- **5-column Kanban board**: Review, Scheduled, Pending, Running, Completed
- **Drag-and-drop**: Move tasks between columns by dragging cards
- **Task categories**: Immediate, Scheduled, and Repeating tasks
- **AI task runner**: Autonomous agent executes tasks using MCP tools, with real-time log streaming
- **Platform integrations**: Pluggable platform abstraction with encrypted credential storage (Twitter/X, Slack)
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
- **Platforms**: Pluggable abstraction layer for external services (Twitter/X, Slack)

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

## Platform Integrations

Platform credentials are configured via **Settings > Platforms** in the web UI. Credentials are encrypted at rest and verified against the platform API before saving.

### Twitter/X

Twitter/X integration enables posting content from tasks.

#### Setting up the X Developer Portal

1. Go to the [X Developer Portal](https://developer.x.com/en/portal/dashboard) and sign in
2. Create a new **Project** and an **App** within it
3. On the app settings page, configure:
   - **App permissions**: Set to **Read and Write** (default is Read-only — posting requires Write)
   - **Type of App**: Select **Web App, Automated App or Bot**
   - **App info**: Fill in the required fields (name, description, website URL)
4. Navigate to **Keys and tokens** and generate:
   - **API Key and Secret** (under Consumer Keys)
   - **Access Token and Secret** (under Authentication Tokens — generate with Read and Write permissions)
5. In the Content Manager UI, go to **Settings > Platforms > Twitter** and enter the four credentials

### Slack

Slack integration enables managing tasks directly from Slack via slash commands: `/task new`, `/task status`, `/task list`, `/task run`, `/task output`.

#### Creating the Slack App

1. Go to the [Slack API dashboard](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, give it a name (e.g. "Content Manager"), and select your workspace
3. Under **OAuth & Permissions**, add the following **Bot Token Scopes**:
   - `commands` — register and receive slash commands
   - `chat:write` — send messages (for future notification support)
   - `users:read.email` — resolve Slack users to email addresses for audit trail
4. Under **Slash Commands**, create a new command:
   - **Command**: `/task`
   - **Request URL**: `https://<your-domain>/slack/commands`
   - **Short Description**: Manage tasks
   - **Usage Hint**: `new <title> | status <id> | list [status] | run <id> | output <id>`
5. Under **Event Subscriptions** (optional, for future use):
   - **Request URL**: `https://<your-domain>/slack/events`
   - The endpoint responds to URL verification automatically
6. Install the app to your workspace — this generates the **Bot Token**
7. Note the **Signing Secret** from **Basic Information > App Credentials**

#### Configuring credentials

In the Content Manager UI, go to **Settings > Platforms > Slack** and enter:

- **Bot Token**: starts with `xoxb-` (from OAuth & Permissions > Bot User OAuth Token)
- **Signing Secret**: from Basic Information > App Credentials

The UI verifies the bot token against the Slack API (`auth.test`) before saving.

#### Slash command reference

| Command | Description |
|---------|-------------|
| `/task new <title>` | Create a new task |
| `/task status <id>` | View task details (accepts UUID prefix, e.g. `a1b2c3`) |
| `/task list [status]` | List tasks, optionally filtered by status |
| `/task run <id>` | Queue a task for execution |
| `/task output <id>` | View task output |
| `/task help` | Show available commands |

All responses are ephemeral (visible only to you). Tasks created or modified via Slack record the user's email in the audit fields (`created_by`/`updated_by`).

## Project Structure

```
backend/          # FastAPI app, SQLAlchemy models, Alembic migrations, worker
  platforms/      # Platform abstraction layer (base, twitter, slack, credentials)
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
# Backend tests (485 tests)
DATABASE_URL="sqlite+aiosqlite:///:memory:" PYTHONPATH=backend \
  backend/.venv/bin/python -m pytest backend/tests/ -v

# Frontend tests (329 tests)
cd frontend && npm test
```
