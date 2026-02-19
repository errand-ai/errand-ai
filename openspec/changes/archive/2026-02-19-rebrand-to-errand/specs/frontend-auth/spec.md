## MODIFIED Requirements

### Requirement: Role extraction from JWT claims
The frontend auth store SHALL extract roles from `resource_access.errand.roles` in the JWT payload (changed from `resource_access['content-manager'].roles`).

#### Scenario: Roles parsed from token
- **WHEN** a JWT contains `{ "resource_access": { "errand": { "roles": ["admin"] } } }`
- **THEN** the auth store exposes `["admin"]` as the user's roles
