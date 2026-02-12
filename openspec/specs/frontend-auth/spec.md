## Requirements

### Requirement: Token extraction from URL fragment
The frontend SHALL check the URL fragment on app load for `access_token`, `id_token`, and `refresh_token` parameters. If an access token is present, the frontend SHALL store all available tokens in the auth store and remove the fragment from the URL.

#### Scenario: Token in fragment after login with refresh token
- **WHEN** the app loads with `/#access_token=eyJ...&id_token=eyJ...&refresh_token=eyR...`
- **THEN** the access token, ID token, and refresh token are stored in the auth store and the URL is cleaned to `/`

#### Scenario: Token in fragment after login without refresh token
- **WHEN** the app loads with `/#access_token=eyJ...&id_token=eyJ...`
- **THEN** the access token and ID token are stored in the auth store (refresh token remains null) and the URL is cleaned to `/`

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
The frontend SHALL attempt a token refresh when any `/api/*` request returns HTTP 401. If the refresh succeeds, the frontend SHALL retry the original request with the new access token. If the refresh fails or no refresh token is available, the frontend SHALL clear the auth store and redirect to `/auth/login`.

#### Scenario: Token expired, refresh succeeds
- **WHEN** an API request returns HTTP 401 and a refresh token is available
- **THEN** the frontend calls `POST /auth/refresh` with the refresh token, updates the stored tokens, and retries the original request

#### Scenario: Token expired, refresh fails
- **WHEN** an API request returns HTTP 401 and the subsequent refresh attempt fails (401 or network error)
- **THEN** the token is cleared from the store and the browser redirects to `/auth/login`

#### Scenario: Token expired, no refresh token available
- **WHEN** an API request returns HTTP 401 and no refresh token is stored
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
The frontend SHALL manage authentication state in a Pinia store (`useAuthStore`) exposing: `token` (the access token or null), `idToken` (the ID token or null), `refreshToken` (the refresh token or null), `isAuthenticated` (boolean computed), `setToken(token, idToken?, refreshToken?)`, and `clearToken()`.

#### Scenario: Store tracks auth state with refresh token
- **WHEN** `setToken("eyJ...", "eyI...", "eyR...")` is called
- **THEN** `token`, `idToken`, and `refreshToken` return their respective values and `isAuthenticated` returns true

#### Scenario: Store tracks auth state without refresh token
- **WHEN** `setToken("eyJ...", "eyI...")` is called without a refresh token
- **THEN** `token` and `idToken` return their values, `refreshToken` returns null, and `isAuthenticated` returns true

#### Scenario: Cleared store
- **WHEN** `clearToken()` is called
- **THEN** `token`, `idToken`, and `refreshToken` return null and `isAuthenticated` returns false

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

### Requirement: Proactive token refresh before expiry
The frontend SHALL decode the access token's `exp` claim and schedule a background refresh 30 seconds before the token expires. When triggered, the frontend SHALL call `POST /auth/refresh` with the stored refresh token and update the auth store with the new tokens. If the refresh fails, the frontend SHALL NOT redirect to login immediately — the 401 retry mechanism handles the next API call.

#### Scenario: Token refreshed before expiry
- **WHEN** the access token is set with an `exp` claim 300 seconds in the future
- **THEN** a refresh is scheduled to fire at 270 seconds (30 seconds before expiry)

#### Scenario: Proactive refresh succeeds
- **WHEN** the scheduled refresh fires and the refresh endpoint returns new tokens
- **THEN** the auth store is updated with the new access token, ID token, and refresh token, and a new refresh timer is scheduled based on the new token's `exp` claim

#### Scenario: Proactive refresh fails
- **WHEN** the scheduled refresh fires and the refresh endpoint returns an error
- **THEN** no redirect occurs; the next API call that receives a 401 will trigger the retry-then-redirect flow

#### Scenario: No refresh token available
- **WHEN** a token is set without a refresh token
- **THEN** no proactive refresh timer is scheduled

#### Scenario: Token refresh timer cleared on logout
- **WHEN** `clearToken()` is called while a refresh timer is active
- **THEN** the pending refresh timer is cancelled
