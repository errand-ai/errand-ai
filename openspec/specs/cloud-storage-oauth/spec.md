## Purpose

OAuth flow surface for cloud-storage providers: integration status reporting, authorize endpoint with cloud-proxy fallback, and token-refresh routing. Google Workspace mode resolution no longer requires `GDRIVE_MCP_URL` — access is via the bundled `gws` CLI.

## Requirements

### Requirement: Integration status endpoint

The status response SHALL include a `mode` field for each provider indicating how the integration is available.

For Google Workspace, the mode SHALL be resolved without requiring `GDRIVE_MCP_URL`:
1. `"direct"` — local client credentials (`GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`) are configured
2. `"cloud"` — no local credentials, but the cloud `PlatformCredential` exists with `status: "connected"`
3. `null` — neither condition met

For OneDrive, the mode resolution requires `ONEDRIVE_MCP_URL` plus either local credentials or a connected cloud `PlatformCredential`.

The Google Workspace status SHALL additionally include a `reauth_required` field indicating whether the stored credentials have fewer scopes than currently required.

#### Scenario: Google Workspace available via direct mode
- **WHEN** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are configured
- **THEN** Google Workspace status includes `"mode": "direct"`, `"available": true`

#### Scenario: Google Workspace available via cloud mode
- **WHEN** local Google credentials are NOT configured
- **AND** cloud `PlatformCredential` exists with `status: "connected"`
- **THEN** Google Workspace status includes `"mode": "cloud"`, `"available": true`

#### Scenario: Google Workspace re-authorization required
- **WHEN** Google Workspace credentials exist but stored scopes do not include all required scopes
- **THEN** status includes `"reauth_required": true`

#### Scenario: Google Workspace scopes current
- **WHEN** Google Workspace credentials exist and stored scopes match or exceed required scopes
- **THEN** status includes `"reauth_required": false`

#### Scenario: OneDrive available via cloud mode
- **WHEN** `MICROSOFT_CLIENT_ID`/`MICROSOFT_CLIENT_SECRET` are NOT configured
- **AND** `ONEDRIVE_MCP_URL` is configured
- **AND** cloud `PlatformCredential` exists with `status: "connected"`
- **THEN** OneDrive status includes `"mode": "cloud"`, `"available": true`

#### Scenario: Provider unavailable
- **WHEN** no local credentials are configured
- **AND** cloud service is not connected
- **THEN** provider status includes `"mode": null`, `"available": false`

### Requirement: Google OAuth scopes

The Google OAuth authorization flow SHALL request the following scopes: `openid`, `email`, `profile`, `https://www.googleapis.com/auth/drive`, `https://www.googleapis.com/auth/gmail.modify`, `https://www.googleapis.com/auth/calendar`, `https://www.googleapis.com/auth/spreadsheets`, `https://www.googleapis.com/auth/documents`, `https://www.googleapis.com/auth/chat.messages`, `https://www.googleapis.com/auth/tasks`, `https://www.googleapis.com/auth/contacts.readonly`.

The granted scopes SHALL be stored in the `PlatformCredential` metadata for stale-scope detection.

#### Scenario: Authorization requests expanded scopes
- **WHEN** a user initiates Google Workspace authorization
- **THEN** the OAuth request includes all required scopes

#### Scenario: Granted scopes stored
- **WHEN** the OAuth callback completes successfully
- **THEN** the granted scopes are stored in the credential metadata

### Requirement: OAuth authorize endpoint

The authorize endpoint SHALL fall back to the cloud-proxy flow when local client credentials are not configured but the cloud service is connected.

The existing direct flow SHALL remain unchanged when local credentials are present — local credentials take priority.

### Requirement: Token refresh

Token refresh SHALL route through errand-cloud when local client credentials are not configured. The worker SHALL send an `oauth_refresh` WebSocket message and await the response before proceeding with task execution.

When local client credentials are configured, the existing direct refresh flow SHALL remain unchanged.

### Requirement: Canonical Google Workspace OAuth provider name on the WebSocket relay

The errand server SHALL use the canonical provider name `google_workspace` in any `oauth_initiate` or `oauth_refresh` WebSocket frame relayed to errand-cloud for the Google integration. The errand server's HTTP API and DB platform_id retain the legacy internal name `google_drive`; the canonical/internal mapping happens only at the WebSocket boundary.

#### Scenario: Canonical OAuth initiation
- **WHEN** the cloud-proxy authorize flow runs for the Google integration
- **THEN** the `oauth_initiate` WebSocket frame carries `provider: "google_workspace"`
- **AND** the redirect URL targets `<cloud_service_url>/oauth/google_workspace/authorize?state=...`

#### Scenario: Canonical OAuth refresh
- **WHEN** the worker triggers a token refresh for the Google integration via the cloud proxy
- **THEN** the `oauth_refresh` WebSocket frame carries `provider: "google_workspace"`

### Requirement: Tolerant `oauth_tokens` reply receiver

The dispatcher for inbound `oauth_tokens` (and `oauth_error`) WebSocket replies SHALL accept either `provider: "google_workspace"` (canonical) OR `provider: "google_drive"` (deprecated alias kept by errand-cloud for backward compatibility). It SHALL normalize the provider name to the internal `"google_drive"` before storing credentials or publishing SSE events, so DB rows and downstream consumers stay on a single identifier.

The dispatcher SHALL additionally capture the granted scopes from the `oauth_tokens` payload (either `granted_scopes` array or space-separated `scope` string) and persist them on the `PlatformCredential` for stale-scope and per-service badge derivation.

#### Scenario: Canonical reply
- **WHEN** an `oauth_tokens` reply arrives carrying `provider: "google_workspace"`
- **THEN** the dispatcher accepts the message
- **AND** stores the credential under `platform_id="google_drive"`
- **AND** publishes `cloud_storage_connected` with `provider="google_drive"`

#### Scenario: Legacy alias reply
- **WHEN** an `oauth_tokens` reply arrives carrying `provider: "google_drive"`
- **THEN** the dispatcher accepts the message and stores credentials identically to the canonical case

#### Scenario: Granted scopes captured
- **WHEN** the `oauth_tokens` payload includes `granted_scopes` (array) or `scope` (space-separated)
- **THEN** the persisted credential's `granted_scopes` field reflects every granted scope verbatim

### Requirement: Granted scopes surfaced in integration status

The `/api/integrations/status` response SHALL include the `granted_scopes` list for the Google integration when credentials exist, so the UI can derive per-service badge state without re-implementing scope logic.

#### Scenario: Granted scopes surfaced
- **WHEN** the integration status endpoint is called and Google credentials with stored `granted_scopes` exist
- **THEN** the `google_drive` entry in the response includes a `granted_scopes` array carrying every persisted scope
