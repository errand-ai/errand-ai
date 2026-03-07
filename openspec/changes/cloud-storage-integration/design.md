## Context

The errand backend and worker need to orchestrate cloud storage access for task-runner agents. Two standalone MCP servers (Google Drive, OneDrive) are being built in separate repositories. This change adds the errand-side integration: OAuth credential management, token refresh, worker injection, Helm deployment, and frontend UI.

The existing codebase has established patterns for all of these concerns:
- **Platform credentials**: `PlatformCredential` model with Fernet encryption (`platforms/credentials.py`)
- **MCP injection**: Worker's `process_task_in_container()` conditionally injects MCP servers (Hindsight, Playwright, errand, LiteLLM)
- **Integration UI**: Settings page with platform cards (GitHub, Twitter, Email)
- **Helm**: Conditional deployments (KEDA), env var injection into server/worker

## Goals / Non-Goals

**Goals:**

- Enable users to connect Google Drive and OneDrive accounts via OAuth 2.0 Authorization Code flow
- Securely store and refresh OAuth tokens using existing credential encryption infrastructure
- Automatically inject cloud storage MCP servers into task-runner containers when credentials are configured
- Extend Helm chart with conditional MCP server deployments
- Provide a clean UI for connecting/disconnecting cloud storage accounts
- Support profile-level control over cloud storage access

**Non-Goals:**

- Building the MCP servers themselves (separate repos)
- Cloud storage browsing UI in the errand frontend
- Multi-account support per provider (one Google Drive account, one OneDrive account)
- Apple Containerization deployment (separate change in errand-desktop)

## Decisions

### 1. OAuth routes as dedicated integration endpoints

**Choice:** New route group at `/api/integrations/{provider}/authorize` and `/api/integrations/{provider}/callback` rather than extending the existing `/auth/` routes.

**Rationale:** The existing `/auth/` routes handle Keycloak SSO for user authentication. Cloud storage OAuth is a different concern — connecting external services, not authenticating users. Separate route namespace keeps the concerns clean. The `{provider}` path parameter supports Google Drive and OneDrive with the same route handlers (parameterized by provider config).

**Alternative considered:** Extending the Platform system with an OAuth flow — the current Platform base class assumes form-based credential input. Adding OAuth redirect flow to Platform would require significant refactoring of the base class and frontend for a pattern used by only 2 of 6 platforms.

### 2. Store OAuth tokens in PlatformCredential

**Choice:** Reuse the existing `PlatformCredential` model and Fernet encryption for storing OAuth tokens.

**Rationale:** The infrastructure exists — encrypted storage, `load_credentials`/`encrypt`/`decrypt` functions. The payload shape differs (tokens + expiry instead of API keys), but the storage mechanism is identical.

Stored payload per provider:
```json
{
  "access_token": "ya29...",
  "refresh_token": "1//...",
  "expires_at": 1709000000,
  "token_type": "Bearer",
  "user_email": "user@example.com",
  "user_name": "Display Name"
}
```

### 3. Token refresh in the worker, not the server

**Choice:** The worker refreshes expired tokens before launching a task-runner container. The server only needs valid tokens to display the integration status.

**Rationale:** The worker is the point where tokens are consumed — it injects them into MCP configs. Refreshing here ensures the token is fresh at injection time. The maximum task duration determines the worst-case token age (typically < 1 hour, which is within the token TTL for both Google and Microsoft).

Token refresh flow:
1. Worker loads credentials from DB
2. Checks `expires_at` vs current time (with 5-minute buffer)
3. If expired: POST to provider's token endpoint with `refresh_token`
4. Update `PlatformCredential` with new `access_token` and `expires_at`
5. Inject fresh token into `mcp.json`

### 4. Two-gate injection pattern

**Choice:** Inject cloud storage MCP servers into task-runner only when both conditions are met: (a) URL env var is set (`GDRIVE_MCP_URL` / `ONEDRIVE_MCP_URL`) and (b) valid credentials exist in the database.

**Rationale:** Matches the established pattern for Hindsight (`HINDSIGHT_URL` + settings). Gate (a) confirms the MCP server is deployed. Gate (b) confirms the user has connected their account. Either gate missing = no injection, no error.

### 5. Integration page availability based on server API

**Choice:** The server exposes a `GET /api/integrations/available` endpoint that reports which cloud storage integrations are available (based on which URL env vars are set and which client credentials are configured). The frontend uses this to enable/grey-out integration cards.

**Rationale:** The frontend cannot directly check env vars. An API endpoint gives the server full control over what's available. This also allows future extension (e.g., admin-disabled integrations).

### 6. Client credentials via environment variables

**Choice:** Google (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) and Microsoft (`MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`) OAuth client credentials are provided as environment variables by the deployer.

**Rationale:** These are deployment-level configuration — the deployer registers their own OAuth apps with Google/Microsoft. Not user-level settings. Environment variables are the established pattern for deployment config (see `OPENAI_BASE_URL`, `OIDC_CLIENT_ID`, etc.).

### 7. Helm: separate Deployment + Service per MCP server

**Choice:** Each MCP server gets its own Deployment and ClusterIP Service within the Helm chart, gated by `gdrive.enabled` and `onedrive.enabled` values.

**Rationale:** Independent scaling, independent lifecycle, independent image versions. The Services provide stable DNS names for env var injection (`http://{{ .Release.Name }}-gdrive-mcp:8080/mcp`).

## Risks / Trade-offs

**[Refresh token revocation]** If a user revokes access to the OAuth app via their Google/Microsoft account settings, the stored refresh token becomes invalid. **Mitigation:** Detect 400/401 on token refresh, mark the integration as disconnected, surface this in the UI. User must re-connect.

**[Client credential setup burden]** Deployers must register OAuth apps with Google and Microsoft, which involves non-trivial setup (consent screen configuration, redirect URIs, etc.). **Mitigation:** Comprehensive documentation with step-by-step setup guides, screenshots, and required scope/redirect URI values.

**[Token expiry during long tasks]** If a task runs longer than the access token TTL (1 hour for Google, configurable for Microsoft), the MCP server will get 401 errors. **Mitigation:** Document this limitation. The system prompt instructs agents to report cloud storage auth failures. Future enhancement: token refresh endpoint callable from the MCP server.

**[Profile migration]** Existing profiles won't have cloud storage MCP server entries. **Mitigation:** The `_profile_mcp_servers` filter is opt-in — if not specified, all injected MCP servers are available. Cloud storage servers automatically appear for profiles with no explicit filter.

## Migration Plan

1. Deploy MCP server containers (Helm chart update)
2. Configure OAuth client credentials as environment variables
3. Deploy errand backend/worker with new code
4. Users connect cloud storage via Settings > Integrations
5. Cloud storage becomes available to task-runner agents automatically

No database migration needed — `PlatformCredential` table already exists. Rollback: remove MCP server deployments, remove env vars. Stored credentials become inert.
