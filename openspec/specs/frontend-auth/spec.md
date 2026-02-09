## Requirements

### Requirement: Token extraction from URL fragment
The frontend SHALL check the URL fragment on app load for an `access_token` parameter. If present, the frontend SHALL store the token in the auth store and remove the fragment from the URL.

#### Scenario: Token in fragment after login
- **WHEN** the app loads with `/#access_token=eyJ...`
- **THEN** the token is stored in the auth store and the URL is cleaned to `/`

#### Scenario: No fragment present
- **WHEN** the app loads without a URL fragment
- **THEN** no token extraction occurs and the app checks existing auth state

### Requirement: Redirect to login when unauthenticated
The frontend SHALL redirect the browser to `/auth/login` when no access token is available in the auth store and no token is present in the URL fragment.

#### Scenario: No token on load
- **WHEN** the app loads with no token in the store and no URL fragment
- **THEN** the browser is redirected to `/auth/login`

#### Scenario: Token exists
- **WHEN** the app loads with a valid token in the auth store
- **THEN** the app renders normally without redirecting

### Requirement: Bearer token on API requests
The frontend SHALL include an `Authorization: Bearer <token>` header on all requests to `/api/*` endpoints when a token is available in the auth store.

#### Scenario: Authenticated API request
- **WHEN** the frontend fetches `/api/tasks` with a token in the auth store
- **THEN** the request includes the header `Authorization: Bearer <token>`

### Requirement: Handle 401 responses
The frontend SHALL clear the auth store and redirect to `/auth/login` when any `/api/*` request returns HTTP 401.

#### Scenario: Token expired during session
- **WHEN** an API request returns HTTP 401
- **THEN** the token is cleared from the store and the browser redirects to `/auth/login`

### Requirement: Handle 403 responses with access denied page
The frontend SHALL display an "Access Denied" page when any `/api/*` request returns HTTP 403. The page SHALL inform the user that they do not have the required roles and SHALL instruct them to contact the administrator for access. The page SHALL include a logout button.

#### Scenario: User has no roles
- **WHEN** an API request returns HTTP 403
- **THEN** the frontend displays the access denied page with the message "You do not have permission to access this application. Please contact your administrator."

#### Scenario: Logout from access denied page
- **WHEN** the user clicks the logout button on the access denied page
- **THEN** the browser navigates to `/auth/logout`

### Requirement: Auth state managed in Pinia store
The frontend SHALL manage authentication state in a Pinia store (`useAuthStore`) exposing: `token` (the access token or null), `isAuthenticated` (boolean computed), `setToken(token)`, and `clearToken()`.

#### Scenario: Store tracks auth state
- **WHEN** `setToken("eyJ...")` is called
- **THEN** `token` returns the value and `isAuthenticated` returns true

#### Scenario: Cleared store
- **WHEN** `clearToken()` is called
- **THEN** `token` returns null and `isAuthenticated` returns false

### Requirement: Logout navigates to backend logout endpoint
The frontend SHALL provide a logout action that redirects the browser to `/auth/logout`.

#### Scenario: User logs out
- **WHEN** the user triggers logout
- **THEN** the browser navigates to `/auth/logout`

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
