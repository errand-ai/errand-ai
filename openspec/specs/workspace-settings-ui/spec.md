# workspace-settings-ui Specification

## Purpose
TBD - created by archiving change shared-cloud-workspace. Update Purpose after archive.
## Requirements
### Requirement: Workspace configuration in admin settings

The settings UI SHALL provide a Shared Workspace section where an admin can view whether the workspace gateway is configured (provider, cloud folder) and see that the feature is opt-in per task profile. Deployment-level gateway settings (provider, folder, ClusterIP) are Helm/compose configuration; the UI SHALL display them read-only rather than editing them.

#### Scenario: Configured workspace displayed

- **WHEN** an admin opens the Shared Workspace settings section on a deployment with the gateway enabled
- **THEN** the provider, cloud folder, and gateway enablement state are shown

#### Scenario: Feature disabled

- **WHEN** the gateway is not deployed
- **THEN** the section states the feature is disabled and links to setup documentation

### Requirement: Gateway health readout

The settings UI SHALL display gateway health: last successful auth/refresh time, pending upload count, and auth state, sourced from the errand server's workspace status endpoint (`WorkspaceGatewayHealth`). Degraded states (auth failure, growing pending uploads, or no recent gateway report) SHALL be visually distinguished so sync breakage is never silent.

#### Scenario: Healthy gateway

- **WHEN** the gateway is authenticated and has no pending uploads
- **THEN** the health readout shows a healthy state with the last successful refresh time

#### Scenario: Auth failure surfaced

- **WHEN** the gateway token refresh has been failing
- **THEN** the health readout shows an auth error state prominently

