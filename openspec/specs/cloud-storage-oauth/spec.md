## ADDED Requirements

### Requirement: OAuth authorize endpoint

The server SHALL expose `GET /api/integrations/{provider}/authorize` (where provider is `google_drive` or `onedrive`) that redirects the user's browser to the provider's OAuth consent screen.

The redirect URL SHALL include the appropriate client_id, redirect_uri, scopes, and `access_type=offline` (Google) or `offline_access` scope (Microsoft) to obtain a refresh token.

#### Scenario: Google Drive authorize
- **WHEN** user requests `GET /api/integrations/google_drive/authorize`
- **AND** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` env vars are configured
- **THEN** server redirects to Google's OAuth authorize URL with scope `https://www.googleapis.com/auth/drive` and `access_type=offline`

#### Scenario: OneDrive authorize
- **WHEN** user requests `GET /api/integrations/onedrive/authorize`
- **AND** `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET` env vars are configured
- **THEN** server redirects to Microsoft's OAuth authorize URL with scopes `Files.ReadWrite.All offline_access`

#### Scenario: Provider not configured
- **WHEN** user requests authorize for a provider whose client credentials are not configured
- **THEN** server returns HTTP 404 with an error message

### Requirement: OAuth callback endpoint

The server SHALL expose `GET /api/integrations/{provider}/callback` that receives the OAuth authorization code, exchanges it for tokens, and stores them encrypted in the database.

The endpoint SHALL store: `access_token`, `refresh_token`, `expires_at`, `token_type`, `user_email` (fetched from provider's user info endpoint), and `user_name`.

After successful storage, the endpoint SHALL redirect the user back to the Settings > Integrations page.

#### Scenario: Successful Google Drive callback
- **WHEN** Google redirects to `/api/integrations/google_drive/callback?code=AUTH_CODE`
- **THEN** server exchanges the code for tokens via Google's token endpoint
- **AND** fetches user info from Google's userinfo endpoint
- **AND** encrypts and stores credentials in `PlatformCredential` with `platform_id="google_drive"`
- **AND** redirects user to the Settings > Integrations page

#### Scenario: Successful OneDrive callback
- **WHEN** Microsoft redirects to `/api/integrations/onedrive/callback?code=AUTH_CODE`
- **THEN** server exchanges the code for tokens via Microsoft's token endpoint
- **AND** fetches user info from Microsoft Graph `/me` endpoint
- **AND** encrypts and stores credentials in `PlatformCredential` with `platform_id="onedrive"`
- **AND** redirects user to the Settings > Integrations page

#### Scenario: OAuth error callback
- **WHEN** the provider redirects with an error parameter (e.g. user denied consent)
- **THEN** server redirects to the Settings > Integrations page with an error indicator

### Requirement: Disconnect endpoint

The server SHALL expose `DELETE /api/integrations/{provider}` that removes the stored credentials for the specified provider.

#### Scenario: Disconnect Google Drive
- **WHEN** user sends `DELETE /api/integrations/google_drive`
- **THEN** server deletes the `PlatformCredential` record for `platform_id="google_drive"`
- **AND** returns HTTP 200

#### Scenario: Disconnect provider not connected
- **WHEN** user sends `DELETE /api/integrations/onedrive` and no OneDrive credentials exist
- **THEN** server returns HTTP 200 (idempotent)

### Requirement: Integration status endpoint

The server SHALL expose `GET /api/integrations/status` that returns the connection status for all cloud storage providers.

The response SHALL include for each provider: `available` (boolean, whether the MCP server URL and client credentials are configured), `connected` (boolean, whether credentials exist), `user_email` (if connected), and `user_name` (if connected).

#### Scenario: Both providers available, Google connected
- **WHEN** `GDRIVE_MCP_URL`, `GOOGLE_CLIENT_ID`, `ONEDRIVE_MCP_URL`, and `MICROSOFT_CLIENT_ID` are all configured
- **AND** Google Drive credentials exist but OneDrive credentials do not
- **THEN** server returns `{"google_drive": {"available": true, "connected": true, "user_email": "...", "user_name": "..."}, "onedrive": {"available": true, "connected": false}}`

#### Scenario: OneDrive not available
- **WHEN** `ONEDRIVE_MCP_URL` or `MICROSOFT_CLIENT_ID` is not configured
- **THEN** OneDrive entry has `"available": false, "connected": false`

### Requirement: Token refresh

The worker SHALL refresh expired OAuth tokens before injecting them into task-runner containers.

When `expires_at` is within 5 minutes of current time, the worker SHALL POST to the provider's token endpoint with the stored `refresh_token`, update the `PlatformCredential` with the new `access_token` and `expires_at`, and use the fresh token for injection.

#### Scenario: Google token expired before task launch
- **WHEN** worker prepares a task-runner container
- **AND** Google Drive credentials exist with `expires_at` in the past
- **THEN** worker refreshes the token via Google's token endpoint
- **AND** updates the stored credentials with the new access_token and expires_at
- **AND** injects the fresh token into the MCP configuration

#### Scenario: Refresh token revoked
- **WHEN** worker attempts to refresh a token and the provider returns an error (e.g. token revoked)
- **THEN** worker logs a warning and skips cloud storage injection for that provider
- **AND** does NOT prevent the task from running (cloud storage is optional)

#### Scenario: Token still valid
- **WHEN** worker prepares a task-runner container
- **AND** credentials exist with `expires_at` more than 5 minutes in the future
- **THEN** worker uses the existing access_token without refreshing
