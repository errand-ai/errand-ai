## MODIFIED Requirements

### Requirement: Auth state managed in Pinia store

_(Append to existing requirement — add role-checking computed properties)_

The auth store SHALL expose an `isEditor` computed property that returns `true` if the `roles` array includes `"editor"` or `"admin"`, and `false` otherwise.

The auth store SHALL expose an `isViewer` computed property that returns `true` if `isAuthenticated` is true and `isEditor` is false, and `false` otherwise. This means a viewer is any authenticated user who is neither an editor nor an admin.

#### Scenario: User is editor
- **WHEN** `roles` contains `"editor"` but not `"admin"`
- **THEN** `isEditor` returns `true` and `isViewer` returns `false`

#### Scenario: Admin is also editor
- **WHEN** `roles` contains `"admin"`
- **THEN** `isEditor` returns `true` (admin is a superset of editor) and `isViewer` returns `false`

#### Scenario: User is viewer only
- **WHEN** `roles` contains `"viewer"` but not `"editor"` or `"admin"`
- **THEN** `isEditor` returns `false` and `isViewer` returns `true`

#### Scenario: Unauthenticated user
- **WHEN** no access token is stored
- **THEN** `isEditor` returns `false` and `isViewer` returns `false`
