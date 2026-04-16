## Purpose

OAuth 2.0 Authorization Code flow (with PKCE) between the backend and the errand-cloud Keycloak realm, including credential persistence, offline token refresh, and SSRF-safe JWT validation.

## Requirements

### Requirement: Cloud OAuth login initiation
The backend SHALL expose `GET /api/cloud/auth/login` requiring the `admin` role. The endpoint SHALL initiate an OAuth 2.0 Authorization Code flow with PKCE against the errand-cloud Keycloak realm.

#### Scenario: Login redirect
- **WHEN** an admin requests `GET /api/cloud/auth/login`
- **THEN** the backend SHALL generate a PKCE code_verifier and code_challenge
- **THEN** the backend SHALL store the code_verifier in a short-lived server-side state (keyed by a state parameter)
- **THEN** the backend SHALL redirect to the Keycloak authorization endpoint with parameters: `client_id`, `redirect_uri` (pointing to `/api/cloud/auth/callback`), `response_type=code`, `scope=openid offline_access`, `code_challenge`, `code_challenge_method=S256`, and `state`

#### Scenario: Cloud not configured
- **WHEN** an admin requests `GET /api/cloud/auth/login` and the cloud service URL or Keycloak configuration is not available
- **THEN** the backend SHALL return HTTP 503 with detail "Cloud service not configured"

### Requirement: Cloud OAuth callback
The backend SHALL expose `GET /api/cloud/auth/callback` that handles the Keycloak redirect after user authentication.

#### Scenario: Successful authentication
- **WHEN** Keycloak redirects to `/api/cloud/auth/callback` with a valid authorization code and state parameter
- **THEN** the backend SHALL exchange the code for tokens using the Keycloak token endpoint with the stored code_verifier (PKCE)
- **THEN** the backend SHALL extract the `sub` claim from the access token as the tenant_id
- **THEN** the backend SHALL encrypt and store `access_token`, `refresh_token`, `token_expiry`, and `tenant_id` as a PlatformCredential with `platform_id = "cloud"` and `status = "connected"`
- **THEN** the backend SHALL start the cloud WebSocket client background task
- **THEN** the backend SHALL trigger cloud endpoint registration if Slack credentials are already configured
- **THEN** the backend SHALL redirect the user to `/settings/cloud`

#### Scenario: Authentication error
- **WHEN** Keycloak redirects with an `error` parameter
- **THEN** the backend SHALL redirect to `/settings/cloud` with an error query parameter

#### Scenario: Invalid state parameter
- **WHEN** the callback receives a state parameter that doesn't match any stored value
- **THEN** the backend SHALL return HTTP 400 with detail "Invalid state parameter"

### Requirement: Cloud disconnect
The backend SHALL expose `POST /api/cloud/auth/disconnect` requiring the `admin` role. The endpoint SHALL disconnect from the cloud service.

#### Scenario: Disconnect while connected
- **WHEN** an admin sends `POST /api/cloud/auth/disconnect` and cloud credentials exist
- **THEN** the backend SHALL stop the cloud WebSocket client background task
- **THEN** the backend SHALL revoke cloud endpoints via `DELETE /api/endpoints?integration=slack` on the cloud service
- **THEN** the backend SHALL delete the cloud PlatformCredential record
- **THEN** the backend SHALL delete the `cloud_endpoints` setting
- **THEN** the backend SHALL publish a `cloud_status` event with status `disconnected`
- **THEN** the backend SHALL return HTTP 200

#### Scenario: Disconnect when not connected
- **WHEN** an admin sends `POST /api/cloud/auth/disconnect` and no cloud credentials exist
- **THEN** the backend SHALL return HTTP 200 (idempotent)

### Requirement: Offline token refresh
A background task SHALL proactively refresh the cloud access token before it expires.

#### Scenario: Token approaching expiry
- **WHEN** the cloud access token will expire within 60 seconds
- **THEN** the refresh task SHALL use the offline refresh token to obtain new tokens from the Keycloak token endpoint
- **THEN** the refresh task SHALL update the encrypted PlatformCredential with the new access_token, refresh_token (if rotated), and token_expiry

#### Scenario: Refresh failure
- **WHEN** the token refresh request fails (network error, revoked token, Keycloak downtime)
- **THEN** the refresh task SHALL log a warning
- **THEN** the existing WebSocket connection SHALL continue until the server closes it
- **THEN** on next reconnection failure, the PlatformCredential status SHALL be set to "error"
- **THEN** a `cloud_status` event SHALL be published with status `error` and appropriate detail

### Requirement: Cloud Keycloak configuration
The backend SHALL support configuration of the cloud Keycloak realm for OAuth flows.

#### Scenario: Default configuration
- **WHEN** the cloud service URL is the default `https://service.errand.cloud`
- **THEN** the Keycloak realm URL, client_id, and discovery endpoint SHALL use the errand-cloud project's shared Keycloak instance defaults

#### Scenario: Custom cloud service
- **WHEN** the `cloud_service_url` setting is overridden
- **THEN** the backend SHALL derive or read the Keycloak configuration from the custom cloud service

### Requirement: JWT issuer validation before JWKS fetch
Before fetching the JWKS endpoint for cloud JWT validation, the system SHALL verify that the `iss` claim in the (unverified) JWT matches the configured cloud Keycloak realm URL. If the issuer does not match the expected value, the system SHALL reject the token with an authentication error without making any outbound network request. The expected issuer SHALL be derived from the existing cloud Keycloak configuration (e.g. `CLOUD_KEYCLOAK_URL` environment variable or equivalent setting) and SHALL NOT be read from the token itself.

#### Scenario: Issuer matches configured realm
- **WHEN** a cloud JWT arrives with `iss` equal to the configured Keycloak realm URL
- **THEN** JWKS fetch proceeds and the token is validated normally

#### Scenario: Issuer does not match configured realm
- **WHEN** a cloud JWT arrives with `iss` pointing to an external or attacker-controlled URL
- **THEN** the system raises `AuthError` without making any outbound HTTP request to the issuer URL

#### Scenario: Issuer validation happens before network call
- **WHEN** a JWT with a mismatched issuer is received
- **THEN** no HTTP request is made to any JWKS endpoint, preventing SSRF

#### Scenario: Missing iss claim rejected
- **WHEN** a cloud JWT does not contain an `iss` claim
- **THEN** the system raises `AuthError`
