## ADDED Requirements

### Requirement: Roles extracted from JWT claims
The auth store SHALL expose a `roles` computed property that extracts the roles array from the access token's JWT payload at the claim path `resource_access.content-manager.roles`. If the token is null or the claim path does not resolve to an array, `roles` SHALL return an empty array.

#### Scenario: Token with roles
- **WHEN** the access token contains `resource_access.content-manager.roles: ["user", "admin"]`
- **THEN** `roles` returns `["user", "admin"]`

#### Scenario: Token with no roles claim
- **WHEN** the access token does not contain the `resource_access.content-manager` claim
- **THEN** `roles` returns `[]`

#### Scenario: No token
- **WHEN** no access token is stored
- **THEN** `roles` returns `[]`

### Requirement: Admin role check
The auth store SHALL expose an `isAdmin` computed property that returns `true` if the `roles` array includes the string `"admin"`, and `false` otherwise.

#### Scenario: User is admin
- **WHEN** `roles` contains `"admin"`
- **THEN** `isAdmin` returns `true`

#### Scenario: User is not admin
- **WHEN** `roles` does not contain `"admin"`
- **THEN** `isAdmin` returns `false`
