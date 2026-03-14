# Errand

Errand AI is a personal task automation platform. You describe what you need done in plain language, and an AI agent takes care of it — researching topics, drafting emails, browsing the web, managing files, interacting with APIs, and much more. It runs on your own hardware, keeping your data under your control.

![Task Board](/images/task-board.png)

## Features

- **5-column Kanban board**: Review, Scheduled, Pending, Running, Completed.
- **Drag-and-drop**: Move tasks between columns by dragging cards.
- **Task categories**: Immediate, Scheduled, and Repeating tasks.
- **Task Profiles**: Define multiple types of tasks, each with their own settings.
- **AI task runner**: Autonomous agent executes tasks using MCP tools, with real-time log streaming.
- **Platform integrations**: Pluggable platform abstraction with encrypted credential storage (Twitter/X, Slack)
- **Cloud Storage**: Full support for Google Drive and OneDrive.
- **MCP Server Integration**: Extend capabilities with MCP for connectivity to external systems.
- **Agent Skills**: Full support for on-demand loading of Agent Skill definitions.
- **AI Native**: Exposes services with it's own MCP server for integration with other AI Coding Tools & Agentic systems.
- **SSO authentication**: Keycloak OIDC with role-based access control (admin/user roles)
- **Audit metadata**: Tasks track created_by/updated_by from authenticated user

## Architecture

![Errand Architecture](/images/architecture.png)

- **Frontend**: Vue 3 SPA served by nginx, communicates with backend via REST API and WebSocket
- **Backend**: FastAPI app handling API endpoints, authentication, and an MCP server for agent tools
- **Worker**: Polls for pending tasks, orchestrates AI agent execution using the MCP SDK
- **Task Runner**: Sandboxed Docker container for executing agent-generated commands
- **Platforms**: Pluggable abstraction layer for external services (Twitter/X, Slack)

## Local Development

Requires Docker and Docker Compose.

```bash
# Start all services (postgres, migrations, backend, worker, frontend, valkey)
docker compose -f testing/docker-compose.yml up --build

# Frontend: http://localhost:8000
# Backend API: http://localhost:8000/api

# Stop and remove containers
docker compose -f testing/docker-compose.yml down
```

### Environment Variables

Create a `.env` file with the required configuration:

```bash
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
