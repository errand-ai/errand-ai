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

The Google OAuth authorization flow SHALL request the following scopes, using the canonical Drive-style URIs for the OpenID Connect identity scopes (Google rewrites the short forms `email` and `profile` to these canonical URIs in its token-response `scope` claim — requesting them up-front keeps the request and the persisted required-set string-equal so stale-scope detection works):

```
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/userinfo.profile
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/chat.messages
https://www.googleapis.com/auth/tasks
https://www.googleapis.com/auth/contacts
```

The granted scopes SHALL be stored in the `PlatformCredential` metadata for stale-scope detection. `_required_scopes("google_drive")` SHALL return the same canonical set.

#### Scenario: Authorization requests canonical OIDC URIs
- **WHEN** a user initiates Google Workspace authorization via the direct flow
- **THEN** the authorize URL's `scope` parameter contains `https://www.googleapis.com/auth/userinfo.email` and `https://www.googleapis.com/auth/userinfo.profile` (NOT the short `email` / `profile` forms)
- **AND** every Workspace scope listed above

#### Scenario: Granted set satisfies required after a successful re-auth
- **WHEN** Google's token response includes the canonical URIs for OIDC scopes
- **AND** every Workspace scope advertised in the consent screen
- **THEN** `_required_scopes("google_drive").issubset(set(granted_scopes))` is `True`
- **AND** the integration status endpoint returns `reauth_required: false`

#### Scenario: Pre-existing credential with short-form OIDC scopes
- **WHEN** a credential persisted by an older version of errand-server has `email` and `profile` in `granted_scopes` instead of the canonical URIs
- **THEN** `reauth_required` remains `true` until the user re-authorises (no migration is performed)
- **AND** the next re-auth populates the canonical URIs and the warning clears for good

### Requirement: OAuth authorize endpoint

The authorize endpoint SHALL fall back to the cloud-proxy flow when local client credentials are not configured but the cloud service is connected.

The existing direct flow SHALL remain unchanged when local credentials are present — local credentials take priority.

#### Scenario: Cloud-proxy fallback when local credentials absent

- **WHEN** a caller hits the authorize endpoint with no local client credentials configured but the cloud service connected
- **THEN** the authorize request routes through the cloud-proxy flow

#### Scenario: Direct flow when local credentials present

- **WHEN** a caller hits the authorize endpoint with local client credentials configured
- **THEN** the existing direct authorize flow is used unchanged
- **AND** local credentials take priority over the cloud-proxy flow

### Requirement: Token refresh

Token refresh SHALL route through errand-cloud when local client credentials are not configured. The worker SHALL send an `oauth_refresh` WebSocket message and await the response before proceeding with task execution.

When local client credentials are configured, the existing direct refresh flow SHALL remain unchanged.

#### Scenario: Refresh via errand-cloud when local credentials absent

- **WHEN** the worker needs a fresh token and no local client credentials are configured
- **THEN** it sends an `oauth_refresh` WebSocket message to errand-cloud
- **AND** awaits the response before proceeding with task execution

#### Scenario: Direct refresh when local credentials present

- **WHEN** the worker needs a fresh token and local client credentials are configured
- **THEN** the existing direct refresh flow is used unchanged

### Requirement: Canonical Google Workspace OAuth provider name on the WebSocket relay

The errand server SHALL use the canonical provider name `google_workspace` in any `oauth_initiate` or `oauth_refresh` WebSocket frame relayed to errand-cloud for the Google integration. The errand server's HTTP API and DB platform_id retain the legacy internal name `google_drive`; the canonical/internal mapping happens only at the WebSocket boundary via `to_wire_provider()` / `from_wire_provider()`.

The cloud-proxy authorize redirect URL returned to the browser SHALL use the canonical `google_workspace` path segment (e.g. `https://service.errand.cloud/oauth/google_workspace/authorize?state=...`). errand-cloud's Google OAuth client has the canonical `…/oauth/google_workspace/callback` redirect URI registered with Google, and errand-cloud builds the redirect_uri sent to Google from the canonical name regardless of which alias the URL path uses.

The pending-response waiter on `client.send_and_await(...)` for `oauth_refresh_result` SHALL be keyed by the canonical provider name so it matches errand-cloud's response (which always uses canonical, regardless of the inbound provider name on `oauth_refresh`).

#### Scenario: Canonical OAuth initiation
- **WHEN** the cloud-proxy authorize flow runs for the Google integration
- **THEN** the `oauth_initiate` WebSocket frame carries `provider: "google_workspace"`
- **AND** the redirect URL returned to the browser is `<cloud_service_url>/oauth/google_workspace/authorize?state=...`

#### Scenario: Canonical OAuth refresh
- **WHEN** the worker triggers a token refresh for the Google integration via the cloud proxy
- **THEN** the `oauth_refresh` WebSocket frame carries `provider: "google_workspace"`
- **AND** the pending-response waiter is registered at key `oauth_refresh_result:google_workspace`
- **AND** errand-cloud's reply with `provider: "google_workspace"` resolves the waiter without timeout

#### Scenario: Refresh failure when waiter mismatch (regression guard)
- **WHEN** the wire frame uses any value that does not match what errand-cloud echoes back on the response
- **THEN** the `client.send_and_await` future is never resolved and the call times out, surfacing as `Cloud proxy refresh failed` and `Cloud storage token refresh failed for google_drive, skipping`
- **THIS** is the symptom that this requirement prevents

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

### Requirement: OneDrive access-token refresh endpoint

The errand server SHALL provide a OneDrive token refresh endpoint parallel to the existing Google refresh endpoint: an authenticated internal caller can request a fresh OneDrive access token, with a force-refresh option that bypasses the freshness buffer. Refresh SHALL flow through the existing errand-cloud OAuth relay using the canonical provider name. Errors from the relay SHALL be returned as structured errors, not silent failures.

#### Scenario: Fresh token issued

- **WHEN** an authorized caller requests a OneDrive token refresh
- **THEN** the endpoint returns a valid access token usable against the Microsoft Graph API

#### Scenario: Relay unavailable

- **WHEN** errand-cloud is unreachable during a refresh request
- **THEN** the endpoint returns a structured error response and logs the failure

### Requirement: Workspace gateway credential for token fetch

The server SHALL support issuing a workspace-scoped bearer credential that the gateway token-refresher uses to call the Google and OneDrive refresh endpoints. The bearer SHALL NOT be the deployment's `mcp_api_key`, SHALL be usable only for token-refresh endpoints, and SHALL follow the existing opaque-bearer pattern (stored server-side with the bearer as lookup key). Its lifetime SHALL cover the long-running gateway (renewed or non-expiring while the workspace is enabled), and disabling the workspace SHALL invalidate it.

#### Scenario: Gateway fetches tokens with scoped bearer

- **WHEN** the refresher sidecar calls a refresh endpoint with the workspace bearer
- **THEN** the request is authorized and a token for the configured provider is returned

#### Scenario: Bearer rejected elsewhere

- **WHEN** the workspace bearer is presented to a non-refresh API endpoint
- **THEN** the request is rejected as unauthorized

