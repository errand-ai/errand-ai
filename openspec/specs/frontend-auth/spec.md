## Purpose

Frontend authentication flow — token extraction from URL fragments, auth mode detection, role-based access, and session management.

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

### Requirement: Frontend boot sequence with auth mode detection
On app load, the frontend SHALL call `GET /api/auth/status` to determine the auth mode. Based on the mode:
- `"setup"` → route to `/setup` (wizard)
- `"local"` → if no token in store, show local login form at `/login`
- `"sso"` → check URL fragment for OIDC callback tokens; if none, redirect to SSO login URL from the status response

The frontend SHALL NOT redirect to `/auth/login` blindly. The boot sequence SHALL set `authMode` in the store before proceeding.

#### Scenario: Setup mode detected
- **WHEN** the app loads and `/api/auth/status` returns `mode: "setup"`
- **THEN** the browser navigates to `/setup`

#### Scenario: Local auth mode, no token
- **WHEN** the app loads, auth status is `"local"`, and no token exists in the store
- **THEN** the browser navigates to `/login`

#### Scenario: Local auth mode, has token
- **WHEN** the app loads, auth status is `"local"`, and a valid token exists in the store
- **THEN** the app renders normally

#### Scenario: SSO mode with callback tokens
- **WHEN** the app loads, auth status is `"sso"`, and the URL fragment contains `access_token`
- **THEN** the tokens are extracted and stored (existing behavior)

#### Scenario: SSO mode, no token
- **WHEN** the app loads, auth status is `"sso"`, no URL fragment, and no stored token
- **THEN** the browser redirects to the SSO login URL

### Requirement: Local login page
The frontend SHALL define a `/login` route rendering a login form with username and password fields. Submitting the form SHALL call `POST /auth/local/login`. On success, the returned JWT SHALL be stored in the auth store and the user SHALL be redirected to `/`. The login page SHALL only be accessible when auth mode is `"local"`.

#### Scenario: Successful local login
- **WHEN** the user submits valid credentials on the login page
- **THEN** the JWT is stored and the user is redirected to `/`

#### Scenario: Failed local login
- **WHEN** the user submits invalid credentials
- **THEN** an error message "Invalid credentials" is displayed

#### Scenario: Login page blocked in SSO mode
- **WHEN** the auth mode is `"sso"` and a user navigates to `/login`
- **THEN** the user is redirected to the SSO login URL

### Requirement: Redirect to login when unauthenticated
The frontend SHALL redirect to the appropriate login flow when no access token is available. In SSO mode, redirect to the SSO login URL. In local mode, redirect to `/login`. In setup mode, redirect to `/setup`.

#### Scenario: No token in local mode
- **WHEN** the app detects no token and auth mode is `"local"`
- **THEN** the browser navigates to `/login`

#### Scenario: No token in SSO mode
- **WHEN** the app detects no token and auth mode is `"sso"`
- **THEN** the browser redirects to `/auth/login`

### Requirement: Bearer token on API requests
The frontend SHALL include an `Authorization: Bearer <token>` header on all requests to `/api/*` endpoints when a token is available in the auth store.

#### Scenario: Authenticated API request
- **WHEN** the frontend fetches `/api/tasks` with a token in the auth store
- **THEN** the request includes the header `Authorization: Bearer <token>`

### Requirement: Handle 401 responses
The frontend SHALL attempt a token refresh when any `/api/*` request returns HTTP 401. If the refresh succeeds, the frontend SHALL retry the original request with the new access token. If the refresh fails or no refresh token is available, the frontend SHALL clear the auth store and redirect the browser based on the current `authMode`:
- When `authMode` is `"sso"`, the browser SHALL navigate to `/auth/login` (the backend OIDC authorization redirect endpoint).
- When `authMode` is any other value (`"local"`, `"setup"`, or `null` before the status fetch completes), the browser SHALL navigate to `/login` (the Vue SPA route that renders the local login page).

#### Scenario: Token expired, refresh succeeds
- **WHEN** an API request returns HTTP 401 and a refresh token is available
- **THEN** the frontend calls `POST /auth/refresh` with the refresh token, updates the stored tokens, and retries the original request

#### Scenario: Token expired, refresh fails in SSO mode
- **WHEN** an API request returns HTTP 401, `authMode` is `"sso"`, and the subsequent refresh attempt fails (401 or network error)
- **THEN** the token is cleared from the store and the browser redirects to `/auth/login`

#### Scenario: Token expired, refresh fails in local mode
- **WHEN** an API request returns HTTP 401, `authMode` is `"local"`, and the subsequent refresh attempt fails (401 or network error)
- **THEN** the token is cleared from the store and the browser redirects to `/login`

#### Scenario: Token expired, no refresh token available in SSO mode
- **WHEN** an API request returns HTTP 401, `authMode` is `"sso"`, and no refresh token is stored
- **THEN** the token is cleared from the store and the browser redirects to `/auth/login`

#### Scenario: Token expired, no refresh token available in local mode
- **WHEN** an API request returns HTTP 401, `authMode` is `"local"`, and no refresh token is stored
- **THEN** the token is cleared from the store and the browser redirects to `/login`

#### Scenario: Token expired before auth mode is known
- **WHEN** an API request returns HTTP 401 and `authMode` is still `null` (the initial `/api/auth/status` request has not yet resolved)
- **THEN** the token is cleared from the store and the browser redirects to `/login`, letting the subsequent boot sequence re-fetch auth status and redirect further if the mode turns out to be `"sso"` or `"setup"`

### Requirement: Handle 403 responses with access denied page
The frontend SHALL display an "Access Denied" page when any `/api/*` request returns HTTP 403. The page SHALL inform the user that they do not have the required roles and SHALL instruct them to contact the administrator for access. The page SHALL include a logout button.

#### Scenario: User has no roles
- **WHEN** an API request returns HTTP 403
- **THEN** the frontend displays the access denied page with the message "You do not have permission to access this application. Please contact your administrator."

#### Scenario: Logout from access denied page
- **WHEN** the user clicks the logout button on the access denied page
- **THEN** the browser navigates to `/auth/logout`

### Requirement: Auth state managed in Pinia store
The frontend SHALL manage authentication state in a Pinia store (`useAuthStore`) exposing: `token` (the access token or null), `idToken` (the ID token or null), `refreshToken` (the refresh token or null), `authMode` (`"setup"` | `"local"` | `"sso"` | `null`), `isAuthenticated` (boolean computed), `setToken(token, idToken?, refreshToken?)`, `clearToken()`, and `setAuthMode(mode)`. The store SHALL also expose all existing computed properties (`roles`, `isAdmin`, `isEditor`, `isViewer`, `userDisplay`).

#### Scenario: Store tracks auth mode
- **WHEN** `setAuthMode("local")` is called
- **THEN** `authMode` returns `"local"`

#### Scenario: Store tracks auth state with refresh token
- **WHEN** `setToken("eyJ...", "eyI...", "eyR...")` is called
- **THEN** `token`, `idToken`, and `refreshToken` return their respective values and `isAuthenticated` returns true

#### Scenario: Cleared store
- **WHEN** `clearToken()` is called
- **THEN** `token`, `idToken`, and `refreshToken` return null and `isAuthenticated` returns false

### Requirement: Logout adapts to auth mode
The logout action SHALL adapt based on auth mode. In SSO mode, it SHALL redirect to `/auth/logout` (existing OIDC logout). In local mode, it SHALL clear the auth store and redirect to `/login`.

#### Scenario: SSO logout
- **WHEN** the user triggers logout in SSO mode
- **THEN** the browser navigates to `/auth/logout` with `id_token_hint`

#### Scenario: Local logout
- **WHEN** the user triggers logout in local auth mode
- **THEN** the auth store is cleared and the browser navigates to `/login`

### Requirement: Roles extracted from JWT claims
The auth store SHALL expose a `roles` computed property that extracts the roles array from the access token's JWT payload at the claim path `resource_access.errand.roles`. If the token is null or the claim path does not resolve to an array, `roles` SHALL return an empty array.

#### Scenario: Token with roles
- **WHEN** the access token contains `resource_access.errand.roles: ["user", "admin"]`
- **THEN** `roles` returns `["user", "admin"]`

#### Scenario: Token with no roles claim
- **WHEN** the access token does not contain the `resource_access.errand` claim
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
