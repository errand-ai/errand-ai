## MODIFIED Requirements

### Requirement: Login endpoint initiates OIDC flow
The backend SHALL expose `GET /auth/login` which redirects the browser to Keycloak's authorization endpoint with `client_id`, `redirect_uri=/auth/callback`, `response_type=code`, and `scope=openid offline_access`.

#### Scenario: Redirect to Keycloak
- **WHEN** a browser requests `GET /auth/login`
- **THEN** the backend responds with HTTP 302 redirecting to Keycloak's authorization endpoint with `scope=openid offline_access` and the other required query parameters

### Requirement: Callback endpoint exchanges code for tokens
The backend SHALL expose `GET /auth/callback` which receives the authorization code from Keycloak, exchanges it for tokens using `client_id` and `client_secret`, and redirects the browser to the frontend root with the access token, ID token, and refresh token (if present) in the URL fragment.

#### Scenario: Successful code exchange with refresh token
- **WHEN** Keycloak redirects to `/auth/callback?code=VALID_CODE` and the token response includes a refresh token
- **THEN** the backend redirects to `/#access_token=<token>&id_token=<id_token>&refresh_token=<refresh_token>`

#### Scenario: Successful code exchange without refresh token
- **WHEN** Keycloak redirects to `/auth/callback?code=VALID_CODE` and the token response does not include a refresh token
- **THEN** the backend redirects to `/#access_token=<token>&id_token=<id_token>` (no refresh_token parameter)

#### Scenario: Invalid or expired code
- **WHEN** Keycloak redirects to `/auth/callback?code=INVALID_CODE`
- **THEN** the backend returns HTTP 401 with an error message

#### Scenario: Error from Keycloak
- **WHEN** Keycloak redirects to `/auth/callback?error=access_denied`
- **THEN** the backend returns HTTP 401 with the error description

## ADDED Requirements

### Requirement: Refresh token endpoint
The backend SHALL expose `POST /auth/refresh` which accepts a JSON body `{"refresh_token": "<token>"}`, exchanges it with Keycloak's token endpoint using `grant_type=refresh_token`, `client_id`, and `client_secret`, and returns the new tokens as JSON.

#### Scenario: Successful refresh
- **WHEN** a POST to `/auth/refresh` includes a valid refresh token
- **THEN** the backend returns HTTP 200 with `{"access_token": "<new_token>", "id_token": "<new_id_token>", "refresh_token": "<new_refresh_token>"}` (refresh_token included only if Keycloak returns one)

#### Scenario: Expired or revoked refresh token
- **WHEN** a POST to `/auth/refresh` includes an expired or revoked refresh token
- **THEN** the backend returns HTTP 401 with `{"detail": "Refresh token expired or revoked"}`

#### Scenario: Missing refresh token in request body
- **WHEN** a POST to `/auth/refresh` has no `refresh_token` field in the body
- **THEN** the backend returns HTTP 400 with `{"detail": "Missing refresh_token"}`

#### Scenario: Keycloak token endpoint unreachable
- **WHEN** a POST to `/auth/refresh` is received but the Keycloak token endpoint is unreachable
- **THEN** the backend returns HTTP 502 with `{"detail": "Token refresh failed"}`
