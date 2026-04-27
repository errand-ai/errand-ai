## Purpose

Helm chart support for cloud-storage MCP servers (currently OneDrive only) and the OAuth client credentials needed for the in-task `gws` CLI and OneDrive MCP integration.

## Requirements

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
