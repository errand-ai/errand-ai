## ADDED Requirements

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
