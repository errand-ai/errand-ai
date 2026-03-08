## ADDED Requirements

### Requirement: Google Drive MCP server Helm deployment

The Helm chart SHALL include a conditional Deployment and Service for the Google Drive MCP server, controlled by `gdrive.enabled` (default: `true`).

When enabled, the chart SHALL inject `GDRIVE_MCP_URL` as an environment variable into both the server and worker deployments.

#### Scenario: Google Drive enabled (default)
- **WHEN** Helm chart is deployed with `gdrive.enabled: true`
- **THEN** chart renders a Deployment and ClusterIP Service for the Google Drive MCP server
- **AND** injects `GDRIVE_MCP_URL` into server and worker deployments pointing to the service

#### Scenario: Google Drive disabled
- **WHEN** Helm chart is deployed with `gdrive.enabled: false`
- **THEN** chart does NOT render Google Drive resources
- **AND** does NOT inject `GDRIVE_MCP_URL` into any deployment

### Requirement: OneDrive MCP server Helm deployment

The Helm chart SHALL include a conditional Deployment and Service for the OneDrive MCP server, controlled by `onedrive.enabled` (default: `true`).

When enabled, the chart SHALL inject `ONEDRIVE_MCP_URL` as an environment variable into both the server and worker deployments.

#### Scenario: OneDrive enabled (default)
- **WHEN** Helm chart is deployed with `onedrive.enabled: true`
- **THEN** chart renders a Deployment and ClusterIP Service for the OneDrive MCP server
- **AND** injects `ONEDRIVE_MCP_URL` into server and worker deployments pointing to the service

#### Scenario: OneDrive disabled
- **WHEN** Helm chart is deployed with `onedrive.enabled: false`
- **THEN** chart does NOT render OneDrive resources
- **AND** does NOT inject `ONEDRIVE_MCP_URL` into any deployment

### Requirement: OAuth client credential secrets

The Helm chart SHALL support injecting Google and Microsoft OAuth client credentials as environment variables into the server deployment.

Credentials SHALL be sourced from Kubernetes secrets referenced in values.

#### Scenario: Google OAuth credentials configured
- **WHEN** `gdrive.existingSecret` is set in values
- **THEN** chart injects `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` from the referenced secret into the server deployment

#### Scenario: Microsoft OAuth credentials configured
- **WHEN** `onedrive.existingSecret` is set in values
- **THEN** chart injects `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID` from the referenced secret into the server deployment
