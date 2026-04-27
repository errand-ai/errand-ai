## REMOVED Requirements

### Requirement: Google Drive MCP server Helm deployment
**Reason**: Google Drive access is now provided via the `gws` CLI binary installed in the task-runner image. The separate gdrive-mcp container is no longer needed.
**Migration**: Remove `gdrive-mcp-deployment.yaml` and `gdrive-mcp-service.yaml` templates. Remove `GDRIVE_MCP_URL` env var injection from server deployment. The `gdrive.enabled` values key becomes unused. Google OAuth secret injection (`gdrive.existingSecret`) remains needed for the OAuth flow.

## MODIFIED Requirements

### Requirement: OAuth client credential secrets
The Helm chart SHALL support injecting Google and Microsoft OAuth client credentials as environment variables into the server deployment.

Credentials SHALL be sourced from Kubernetes secrets referenced in values.

#### Scenario: Google OAuth credentials configured
- **WHEN** `gdrive.existingSecret` is set in values
- **THEN** chart injects `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` from the referenced secret into the server deployment

#### Scenario: Microsoft OAuth credentials configured
- **WHEN** `onedrive.existingSecret` is set in values
- **THEN** chart injects `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID` from the referenced secret into the server deployment
