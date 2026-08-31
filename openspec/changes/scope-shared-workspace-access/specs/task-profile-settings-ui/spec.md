## ADDED Requirements

### Requirement: Profile settings expose the read-only workspace toggle

The task profile settings UI SHALL expose `shared_workspace_read_only` as a control alongside the existing shared-workspace enable and subpath controls, so that the setting is reachable without calling the API directly.

The control SHALL be presented only when the shared workspace is enabled for the profile, and its wording SHALL make clear that it governs the profile's ability to modify the user's workspace files.

#### Scenario: Toggle shown for a workspace-enabled profile

- **WHEN** an admin edits a profile with the shared workspace enabled
- **THEN** a read-only workspace control is shown beside the workspace enable and subpath controls

#### Scenario: Toggle hidden when the workspace is disabled

- **WHEN** an admin edits a profile with the shared workspace disabled
- **THEN** the read-only control is not shown

#### Scenario: Toggle round-trips through the API

- **WHEN** an admin enables the read-only control and saves
- **THEN** the profile is persisted with `shared_workspace_read_only=true`
- **AND** re-opening the profile shows the control enabled
