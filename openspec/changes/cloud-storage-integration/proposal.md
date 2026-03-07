# Proposal: Cloud Storage Integration

## Problem

Task-runner agents are ephemeral — they have no persistent storage and can only interact with git repositories. Users want agents to read, create, modify, and delete files in their cloud storage (Google Drive, Microsoft OneDrive), enabling:

- Agents that read source documents from cloud storage and produce deliverables
- Multiple agents collaborating in parallel on different files in a shared folder
- Cross-task workflows where one task produces output that another task consumes

## Solution

Add cloud storage integration to errand, connecting task-runner agents to two new standalone MCP servers (`google-drive-mcp-server` and `one-drive-mcp-server`) via the existing MCP injection pattern.

### Components

**1. OAuth Integration Routes (Backend)**

New routes for Google Drive and OneDrive OAuth 2.0 Authorization Code flow:

- `GET /api/integrations/{provider}/authorize` — generate OAuth authorize URL, redirect user to consent screen
- `GET /api/integrations/{provider}/callback` — exchange auth code for tokens, encrypt and store in `PlatformCredential`

OAuth client credentials (client_id, client_secret, tenant_id) provided by the deployer via environment variables — the user completes the interactive consent flow in their browser.

Google scopes: `https://www.googleapis.com/auth/drive` with `access_type=offline` for refresh token.
Microsoft scopes: `Files.ReadWrite.All offline_access`.

**2. Settings UI — Integration Cards (Frontend)**

New integration cards on the Settings > Integrations page for Google Drive and OneDrive:

- "Connect" button triggers OAuth redirect flow
- Shows connected user email/name after successful auth
- "Disconnect" button removes stored credentials
- Cards greyed out with explanatory text when the corresponding MCP server URL env var is not configured (server reports available integrations via an API endpoint)

**3. Token Refresh in Worker**

Before launching a task-runner container, the worker:

- Loads cloud storage credentials from `PlatformCredential` (via the existing `load_credentials` pattern)
- Checks token expiry; if expired, refreshes using the stored refresh token and updates the DB
- Injects fresh access token into the task-runner's `mcp.json` config

**4. Worker MCP Injection**

Same pattern as Hindsight, Playwright, and errand MCP injection in `process_task_in_container()`:

- `GDRIVE_MCP_URL` env var → if set AND Google Drive credentials exist → inject `google_drive` server into `mcp.json` with Bearer token header
- `ONEDRIVE_MCP_URL` env var → if set AND OneDrive credentials exist → inject `onedrive` server into `mcp.json` with Bearer token header

Two-gate pattern: env var present (MCP server deployed) AND credentials configured (user has connected).

**5. Helm Chart Extensions**

Conditional deployments for each MCP server, enabled by default:

```yaml
gdrive:
  enabled: true
  image:
    repository: ghcr.io/devops-consultants/google-drive-mcp-server
    tag: ""
  port: 8080

onedrive:
  enabled: true
  image:
    repository: ghcr.io/devops-consultants/one-drive-mcp-server
    tag: ""
  port: 8080
```

When enabled: renders Deployment + Service, injects `GDRIVE_MCP_URL` / `ONEDRIVE_MCP_URL` into server and worker deployments. When disabled: no resources created, no env vars, integration cards greyed out.

**6. System Prompt Instructions**

When cloud storage MCP servers are injected, append instructions to the task-runner system prompt explaining:

- Available cloud storage tools and their path-based interface
- The ETag-based optimistic concurrency pattern (read returns etag, pass it to write to detect conflicts)
- How to handle permission errors and conflict errors
- Best practice: download file → modify locally → upload (not in-place editing)

**7. Profile-Level Control**

Cloud storage MCP servers participate in the existing `_profile_mcp_servers` filtering — profiles can include/exclude `google_drive` and `onedrive` like any other MCP server.

### Environment Variables

For errand-server and worker:

| Variable | Purpose |
|----------|---------|
| `GDRIVE_MCP_URL` | URL of Google Drive MCP server (e.g. `http://errand-gdrive-mcp:8080/mcp`) |
| `ONEDRIVE_MCP_URL` | URL of OneDrive MCP server (e.g. `http://errand-onedrive-mcp:8080/mcp`) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (deployer provides) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret (deployer provides) |
| `MICROSOFT_CLIENT_ID` | Microsoft OAuth client ID (deployer provides) |
| `MICROSOFT_CLIENT_SECRET` | Microsoft OAuth client secret (deployer provides) |
| `MICROSOFT_TENANT_ID` | Microsoft Entra tenant ID (deployer provides, or `common` for multi-tenant) |

## Non-Goals

- Building the MCP servers themselves (separate repos/changes)
- Binary file format conversion (DOCX, PDF) — future enhancement
- Cloud storage browsing UI in the errand frontend
- Quota management or storage usage monitoring
