# Errand

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
OIDC_CLIENT_ID=errand
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
kubectl create secret generic errand-credential-key \
  --from-literal=encryption-key="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  -n errand
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
5. In the Errand UI, go to **Settings > Platforms > Twitter** and enter the four credentials

### Slack

Slack integration enables managing tasks from Slack via slash commands and @mentions. Task confirmations include interactive buttons and update automatically as task status changes.

- **Slash commands**: `/task new`, `/task status`, `/task list`, `/task run`, `/task output`
- **@mentions**: Mention the bot in any channel to create a task from the message text
- **Interactive buttons**: View Status and View Output buttons on task confirmations
- **Live status updates**: Slack messages update automatically when task status changes (e.g. pending → running → completed)

#### Creating the Slack App

1. Go to the [Slack API dashboard](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, give it a name (e.g. "H.A.L."), and select your workspace
3. Under **OAuth & Permissions**, add the following **Bot Token Scopes**:
   - `commands` — register and receive slash commands
   - `chat:write` — post and update messages in channels
   - `users:read` — resolve user IDs to profile information
   - `users:read.email` — resolve Slack users to email addresses for audit trail
   - `app_mentions:read` — receive @mention events
4. Under **Slash Commands**, create a new command:
   - **Command**: `/task`
   - **Request URL**: `https://<your-domain>/slack/commands`
   - **Short Description**: Manage tasks
   - **Usage Hint**: `new <title> | status <id> | list [status] | run <id> | output <id>`
5. Under **Event Subscriptions**:
   - Enable events and set the **Request URL** to `https://<your-domain>/slack/events`
   - The endpoint responds to URL verification automatically
   - Under **Subscribe to bot events**, add `app_mention`
6. Under **Interactivity & Shortcuts**:
   - Enable interactivity and set the **Request URL** to `https://<your-domain>/slack/interactions`
7. Install the app to your workspace — this generates the **Bot Token**
8. Note the **Signing Secret** from **Basic Information > App Credentials**

#### Configuring credentials

In the Errand UI, go to **Settings > Platforms > Slack** and enter:

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

#### @mention usage

Mention the bot in any channel to create a task:

```
@H.A.L. Deploy the new version to staging
```

The bot posts a confirmation message with task details and interactive buttons. The message updates automatically as the task progresses through statuses.

#### Behaviour notes

- Slash command responses are **ephemeral** (visible only to you) and do not auto-update
- @mention confirmations are **posted to the channel** and update in real-time as task status changes
- All Slack-originated tasks are automatically tagged with `slack`
- Tasks created via Slack record the user's email in the audit fields (`created_by`/`updated_by`)

### Google Drive

Google Drive integration gives task-runner agents read/write access to files in a user's Google Drive via a dedicated MCP server.

#### Prerequisites

- The Google Drive MCP server must be deployed (enabled by default in the Helm chart, or via docker-compose)
- An OAuth 2.0 client must be registered in the Google Cloud Console

#### Creating Google OAuth credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and select or create a project
2. Navigate to **APIs & Services > OAuth consent screen**
   - Choose **External** user type (or **Internal** if using Google Workspace)
   - Fill in the app name, user support email, and developer contact email
   - On the **Scopes** step, add `https://www.googleapis.com/auth/drive`
   - Add any test users if the app is in "Testing" publishing status
3. Navigate to **APIs & Services > Credentials** and click **Create Credentials > OAuth client ID**
   - **Application type**: Web application
   - **Authorized redirect URIs**: Add `https://<your-domain>/api/integrations/google_drive/callback`
   - Note the **Client ID** and **Client Secret**
4. Navigate to **APIs & Services > Enabled APIs** and enable the **Google Drive API**

#### Configuration

Provide the credentials as environment variables to the Errand server:

| Variable | Value |
|----------|-------|
| `GOOGLE_CLIENT_ID` | OAuth Client ID from step 3 |
| `GOOGLE_CLIENT_SECRET` | OAuth Client Secret from step 3 |

For Kubernetes, create a secret and set `gdrive.existingSecret` in your Helm values. The secret must contain keys `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

#### Connecting

Once configured, go to **Settings > Integrations** in the Errand UI. The Google Drive card will show a **Connect** button. Clicking it starts the OAuth consent flow — after granting access, you'll be redirected back to Errand with the connection established.

### OneDrive

OneDrive integration gives task-runner agents read/write access to files in a user's OneDrive via a dedicated MCP server.

#### Prerequisites

- The OneDrive MCP server must be deployed (enabled by default in the Helm chart, or via docker-compose)
- An OAuth 2.0 app registration must be created in Microsoft Entra ID (Azure AD)

#### Creating Microsoft OAuth credentials

1. Go to the [Microsoft Entra admin center](https://entra.microsoft.com/) and navigate to **Identity > Applications > App registrations**
2. Click **New registration**
   - **Name**: e.g. "Errand OneDrive"
   - **Supported account types**: Choose based on your needs
     - *Single tenant* — only users in your organization
     - *Multitenant* — users in any Microsoft Entra directory
     - *Multitenant + personal* — broadest access including personal Microsoft accounts
   - **Redirect URI**: Select **Web** and enter `https://<your-domain>/api/integrations/onedrive/callback`
3. After creation, note the **Application (client) ID** and **Directory (tenant) ID** from the Overview page
4. Navigate to **Certificates & secrets > Client secrets** and click **New client secret**
   - Note the **Value** (this is the client secret — it's only shown once)
5. Navigate to **API permissions** and click **Add a permission**
   - Select **Microsoft Graph > Delegated permissions**
   - Add `Files.ReadWrite.All` and `offline_access`
   - Click **Grant admin consent** if you have admin privileges (otherwise users will be prompted)

#### Configuration

Provide the credentials as environment variables to the Errand server:

| Variable | Value |
|----------|-------|
| `MICROSOFT_CLIENT_ID` | Application (client) ID from step 3 |
| `MICROSOFT_CLIENT_SECRET` | Client secret value from step 4 |
| `MICROSOFT_TENANT_ID` | Directory (tenant) ID from step 3, or `common` for multi-tenant |

For Kubernetes, create a secret and set `onedrive.existingSecret` in your Helm values. The secret must contain keys `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, and `MICROSOFT_TENANT_ID`.

#### Connecting

Once configured, go to **Settings > Integrations** in the Errand UI. The OneDrive card will show a **Connect** button. Clicking it starts the OAuth consent flow — after granting access, you'll be redirected back to Errand with the connection established.

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
