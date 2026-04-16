## MODIFIED Requirements

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
