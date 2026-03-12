## ADDED Requirements

### Requirement: Cloud-proxy OAuth initiation

When a user initiates an OAuth authorize flow for a provider that has no local client credentials but errand-cloud is connected, the server SHALL send an `oauth_initiate` WebSocket message to errand-cloud containing a random state token and the provider name, then redirect the user to errand-cloud's OAuth authorize URL with that state.

#### Scenario: Google Drive authorize via cloud proxy
- **WHEN** user requests `GET /api/integrations/google_drive/authorize`
- **AND** `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are NOT configured
- **AND** the cloud PlatformCredential exists with `status: "connected"`
- **THEN** server generates a random state token
- **AND** sends `{"type": "oauth_initiate", "state": "<token>", "provider": "google_drive"}` over the cloud WebSocket
- **AND** redirects user to `{cloud_service_url}/oauth/google_drive/authorize?state=<token>`

#### Scenario: Neither local credentials nor cloud available
- **WHEN** user requests `GET /api/integrations/google_drive/authorize`
- **AND** `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are NOT configured
- **AND** no cloud service is connected
- **THEN** server returns HTTP 404 with error "Provider not configured — configure client credentials or connect to errand cloud"

### Requirement: WebSocket token reception

The cloud WebSocket client SHALL handle `oauth_tokens` messages from errand-cloud, storing the received credentials in the `PlatformCredential` table using the same encryption as the direct OAuth flow.

#### Scenario: Receive Google Drive tokens via WebSocket
- **WHEN** errand-cloud sends `{"type": "oauth_tokens", "state": "...", "provider": "google_drive", "access_token": "...", "refresh_token": "...", "expires_in": 3600, "user_email": "user@gmail.com", "user_name": "User"}`
- **THEN** server encrypts and stores the credentials in `PlatformCredential` with `platform_id="google_drive"` and `status="connected"`
- **AND** publishes a `cloud_storage_connected` SSE event with the provider name

#### Scenario: Receive OAuth error via WebSocket
- **WHEN** errand-cloud sends `{"type": "oauth_error", "state": "...", "provider": "google_drive", "error": "consent_denied"}`
- **THEN** server logs the error
- **AND** publishes a `cloud_storage_error` SSE event with the provider and error

### Requirement: Cloud-proxy token refresh

When refreshing an expired token for a provider that has no local client credentials, the server SHALL request a refresh through errand-cloud over the WebSocket instead of calling the provider's token endpoint directly.

#### Scenario: Refresh Google Drive token via cloud proxy
- **WHEN** the worker detects an expired Google Drive token
- **AND** `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are NOT configured
- **AND** the cloud WebSocket is connected
- **THEN** server sends `{"type": "oauth_refresh", "provider": "google_drive", "refresh_token": "..."}` over the cloud WebSocket
- **AND** awaits `oauth_refresh_result` response
- **AND** updates the stored credentials with the new `access_token`, `refresh_token` (if rotated), and `expires_at`

#### Scenario: Cloud-proxy refresh fails
- **WHEN** the worker sends an `oauth_refresh` message
- **AND** errand-cloud responds with `{"type": "oauth_error", "provider": "google_drive", "error": "refresh_failed"}`
- **THEN** server logs a warning
- **AND** skips cloud storage injection for that provider (task continues without it)

#### Scenario: Cloud WebSocket not connected during refresh
- **WHEN** the worker detects an expired token
- **AND** no local credentials are configured
- **AND** the cloud WebSocket is not connected
- **THEN** server logs a warning and skips cloud storage injection for that provider
