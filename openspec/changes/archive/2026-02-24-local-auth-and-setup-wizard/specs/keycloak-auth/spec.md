## MODIFIED Requirements

### Requirement: OIDC configuration via environment variables
The backend SHALL read `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET` from environment variables. These are NOT required — if any is missing, the backend SHALL check the database settings table for equivalent keys (`oidc_discovery_url`, `oidc_client_id`, `oidc_client_secret`). If neither env vars nor DB settings provide OIDC configuration, the backend SHALL start without SSO (local auth or setup mode). The backend SHALL also read `OIDC_ROLES_CLAIM` (optional, defaulting to `resource_access.errand.roles`) from env vars or the DB setting `oidc_roles_claim`.

#### Scenario: All required variables set via env
- **WHEN** all three required OIDC environment variables are set
- **THEN** the backend starts with SSO enabled using env-sourced config

#### Scenario: OIDC config from database
- **WHEN** OIDC env vars are not set but `oidc_discovery_url`, `oidc_client_id`, and `oidc_client_secret` exist in the settings table
- **THEN** the backend starts with SSO enabled using DB-sourced config

#### Scenario: No OIDC config anywhere
- **WHEN** neither OIDC env vars nor DB settings are present
- **THEN** the backend starts without SSO (local auth or setup mode depending on whether a local admin exists)

#### Scenario: Custom roles claim path
- **WHEN** `OIDC_ROLES_CLAIM` is set to `resource_access.my-client.roles`
- **THEN** the backend extracts roles from that path in the JWT

### Requirement: OIDC discovery at startup
The backend SHALL fetch the OIDC configuration from the discovery URL at startup and cache the authorization endpoint, token endpoint, JWKS URI, and end-session endpoint. If the discovery fetch fails and OIDC is configured, the backend SHALL log an error and start without SSO (falling back to local auth) rather than failing to start entirely.

#### Scenario: Successful discovery
- **WHEN** the backend starts with a valid OIDC discovery URL
- **THEN** it fetches the well-known configuration and resolves all required OIDC endpoints

#### Scenario: Discovery URL unreachable
- **WHEN** the backend starts and the discovery URL is unreachable
- **THEN** the backend logs an error and starts without SSO enabled

### Requirement: Hot-reload OIDC configuration
The backend SHALL support hot-reloading OIDC configuration when the admin saves SSO settings via the User Management page. The hot-reload SHALL perform OIDC discovery, and on success, atomically swap the module-level `oidc` variable. On failure, the existing auth mode SHALL be preserved and an error returned to the client.

#### Scenario: Hot-reload succeeds
- **WHEN** the admin saves valid OIDC settings via the API and the discovery URL is reachable
- **THEN** the backend switches to SSO mode without requiring a restart

#### Scenario: Hot-reload fails
- **WHEN** the admin saves OIDC settings but the discovery URL is unreachable
- **THEN** the backend returns an error, and the previous auth mode is preserved

### Requirement: JWT validation supports both OIDC and local tokens
The `get_current_user` dependency SHALL validate JWTs from both sources: OIDC tokens (verified via JWKS public keys) and local auth tokens (verified via HMAC with the `jwt_signing_secret`). The dependency SHALL distinguish token type by checking for the `iss` claim — local tokens have issuer `errand-local`, OIDC tokens have the IdP issuer.

#### Scenario: OIDC token validated
- **WHEN** a request includes a JWT with an issuer matching the OIDC configuration
- **THEN** the token is validated against JWKS public keys

#### Scenario: Local token validated
- **WHEN** a request includes a JWT with issuer `errand-local`
- **THEN** the token is validated against the HMAC signing secret

#### Scenario: Unknown issuer rejected
- **WHEN** a request includes a JWT with an unrecognized issuer
- **THEN** the backend returns HTTP 401

## REMOVED Requirements

### Requirement: OIDC configuration via environment variables (original — all three required)
**Reason**: OIDC env vars are no longer required for startup. The backend can also source OIDC config from the database, and can start without SSO entirely.
**Migration**: The startup logic now checks env vars → DB → no SSO, instead of failing when env vars are missing.

### Requirement: OIDC discovery at startup (original — fail to start on failure)
**Reason**: The backend no longer fails to start when OIDC discovery fails. It falls back to local auth mode.
**Migration**: Discovery failure is logged as an error instead of causing a startup crash.
