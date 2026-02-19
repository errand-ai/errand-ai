## MODIFIED Requirements

### Requirement: Roles extraction from JWT
The default OIDC roles claim path SHALL be `resource_access.errand.roles` (changed from `resource_access.content-manager.roles`). The claim path SHALL remain configurable via the `OIDC_ROLES_CLAIM` environment variable.

#### Scenario: Default roles claim
- **WHEN** no `OIDC_ROLES_CLAIM` env var is set
- **THEN** roles are extracted from `resource_access.errand.roles` in the JWT payload

### Requirement: OIDC client identity
The default `OIDC_CLIENT_ID` SHALL be `errand` (changed from `content-manager`). The client ID SHALL remain configurable via the `OIDC_CLIENT_ID` environment variable.

#### Scenario: Default client ID
- **WHEN** no `OIDC_CLIENT_ID` env var is set and the backend initiates an OIDC login
- **THEN** the authorization request uses `client_id=errand`
