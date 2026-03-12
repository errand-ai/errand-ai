## MODIFIED Requirements

### Requirement: Integration status endpoint (MODIFIED)

The status response SHALL include a `mode` field for each provider indicating how the integration is available.

The mode SHALL be resolved in priority order:
1. `"direct"` — local client credentials (`{PROVIDER}_CLIENT_ID` + `{PROVIDER}_CLIENT_SECRET`) and MCP URL are configured
2. `"cloud"` — no local credentials, but the cloud `PlatformCredential` exists with `status: "connected"` and the MCP URL is configured
3. `null` — neither condition met

#### Scenario: Google Drive available via direct mode
- **WHEN** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GDRIVE_MCP_URL` are all configured
- **THEN** Google Drive status includes `"mode": "direct"`, `"available": true`

#### Scenario: OneDrive available via cloud mode
- **WHEN** `MICROSOFT_CLIENT_ID`/`MICROSOFT_CLIENT_SECRET` are NOT configured
- **AND** `ONEDRIVE_MCP_URL` is configured
- **AND** cloud `PlatformCredential` exists with `status: "connected"`
- **THEN** OneDrive status includes `"mode": "cloud"`, `"available": true`

#### Scenario: Provider unavailable
- **WHEN** no local credentials are configured
- **AND** cloud service is not connected (or MCP URL is not configured)
- **THEN** provider status includes `"mode": null`, `"available": false`

### Requirement: OAuth authorize endpoint (MODIFIED)

The authorize endpoint SHALL fall back to the cloud-proxy flow when local client credentials are not configured but the cloud service is connected.

The existing direct flow SHALL remain unchanged when local credentials are present — local credentials take priority.

### Requirement: Token refresh (MODIFIED)

Token refresh SHALL route through errand-cloud when local client credentials are not configured. The worker SHALL send an `oauth_refresh` WebSocket message and await the response before proceeding with task execution.

When local client credentials are configured, the existing direct refresh flow SHALL remain unchanged.
