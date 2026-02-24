## MODIFIED Requirements

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

### Requirement: Logout adapts to auth mode
The logout action SHALL adapt based on auth mode. In SSO mode, it SHALL redirect to `/auth/logout` (existing OIDC logout). In local mode, it SHALL clear the auth store and redirect to `/login`.

#### Scenario: SSO logout
- **WHEN** the user triggers logout in SSO mode
- **THEN** the browser navigates to `/auth/logout` with `id_token_hint`

#### Scenario: Local logout
- **WHEN** the user triggers logout in local auth mode
- **THEN** the auth store is cleared and the browser navigates to `/login`

## REMOVED Requirements

### Requirement: Redirect to login when unauthenticated (original — blind redirect to /auth/login)
**Reason**: The frontend no longer blindly redirects to `/auth/login`. It first calls `/api/auth/status` and routes appropriately.
**Migration**: App.vue boot sequence rewritten to call auth status first.
