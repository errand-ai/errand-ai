## ADDED Requirements

### Requirement: OIDC discovery at startup
The backend SHALL fetch the OIDC configuration from `OIDC_DISCOVERY_URL` at startup and cache the authorization endpoint, token endpoint, JWKS URI, and end-session endpoint. If the discovery fetch fails, the backend SHALL fail to start.

#### Scenario: Successful discovery
- **WHEN** the backend starts with a valid `OIDC_DISCOVERY_URL`
- **THEN** it fetches the well-known configuration and resolves all required OIDC endpoints

#### Scenario: Discovery URL unreachable
- **WHEN** the backend starts and the discovery URL is unreachable
- **THEN** the backend exits with an error indicating OIDC discovery failed

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

### Requirement: Logout endpoint ends session
The backend SHALL expose `GET /auth/logout` which redirects the browser to Keycloak's end-session endpoint with `post_logout_redirect_uri` pointing back to the frontend root.

#### Scenario: Logout redirect
- **WHEN** a browser requests `GET /auth/logout`
- **THEN** the backend responds with HTTP 302 redirecting to Keycloak's end-session endpoint

### Requirement: JWT validation middleware on /api/* routes
The backend SHALL validate the `Authorization: Bearer <token>` header on all requests matching `/api/*` except `/api/health`. Validation SHALL verify the token signature using Keycloak's JWKS public keys, the issuer, the audience (client_id), and the expiration. After signature validation, the middleware SHALL extract the roles claim (at the dot-path configured by `OIDC_ROLES_CLAIM`, defaulting to `resource_access.errand.roles`). If the roles claim is missing or contains no roles, the backend SHALL return HTTP 403.

#### Scenario: Valid token with roles
- **WHEN** a request to `/api/tasks` includes a valid Bearer token containing at least one role
- **THEN** the request proceeds to the route handler

#### Scenario: Valid token with no roles
- **WHEN** a request to `/api/tasks` includes a valid Bearer token with an empty or missing roles claim
- **THEN** the backend returns HTTP 403 with `{"detail": "No roles assigned. Contact your administrator for access."}`

#### Scenario: Missing token
- **WHEN** a request to `/api/tasks` has no Authorization header
- **THEN** the backend returns HTTP 401 with `{"detail": "Not authenticated"}`

#### Scenario: Expired token
- **WHEN** a request to `/api/tasks` includes an expired Bearer token
- **THEN** the backend returns HTTP 401 with `{"detail": "Token expired"}`

#### Scenario: Invalid signature
- **WHEN** a request to `/api/tasks` includes a token with an invalid signature
- **THEN** the backend returns HTTP 401 with `{"detail": "Invalid token"}`

#### Scenario: Health endpoint is exempt
- **WHEN** a request to `/api/health` has no Authorization header
- **THEN** the request proceeds normally and returns the health status

### Requirement: JWKS key caching with refresh on failure
The backend SHALL cache JWKS public keys in memory. If a token's `kid` does not match any cached key, the backend SHALL re-fetch the JWKS once before rejecting the token.

#### Scenario: Key rotation
- **WHEN** Keycloak rotates its signing keys and a token signed with the new key is presented
- **THEN** the backend re-fetches JWKS, finds the new key, and validates the token successfully

#### Scenario: Truly invalid key
- **WHEN** a token has a `kid` not found in JWKS even after re-fetching
- **THEN** the backend returns HTTP 401

### Requirement: OIDC configuration via environment variables
The backend SHALL read `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET` from environment variables. All three are required — if any is missing, the backend SHALL fail to start. The backend SHALL also read `OIDC_ROLES_CLAIM` (optional, defaulting to `resource_access.errand.roles`) to configure the dot-path used to extract roles from the JWT.

#### Scenario: All required variables set
- **WHEN** all three required OIDC environment variables are set
- **THEN** the backend starts and configures OIDC authentication with the default roles claim path

#### Scenario: Custom roles claim path
- **WHEN** `OIDC_ROLES_CLAIM` is set to `resource_access.my-client.roles`
- **THEN** the backend extracts roles from that path in the JWT

#### Scenario: Missing required variable
- **WHEN** `OIDC_CLIENT_SECRET` is not set
- **THEN** the backend exits with an error indicating the missing variable

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
