## ADDED Requirements

### Requirement: Cloud-trusted JWT authentication mode

The backend SHALL support a "cloud-trusted" authentication mode where requests arriving through the cloud tunnel include an `X-Cloud-JWT` header containing the user's Keycloak JWT from errand-cloud.

The auth dependency chain SHALL check for `X-Cloud-JWT` before falling back to local/SSO auth. When present, the server SHALL:
- Validate the JWT against the errand-cloud Keycloak realm's JWKS endpoint
- Extract the user identity (subject claim) for audit logging
- Cache the JWKS with a configurable TTL (default: 3600 seconds)

The JWKS endpoint URL SHALL be derived from the cloud service URL stored in the cloud platform credential configuration: `{cloud_service_url}/.well-known/jwks.json` or from the Keycloak issuer URL in the JWT's `iss` claim.

#### Scenario: Valid cloud JWT accepted

- **WHEN** a request includes `X-Cloud-JWT` header with a valid, non-expired Keycloak JWT
- **THEN** the server validates the JWT against the cloud Keycloak JWKS
- **AND** the request is authenticated with the user identity from the JWT's `sub` claim

#### Scenario: Expired cloud JWT rejected

- **WHEN** a request includes `X-Cloud-JWT` header with an expired JWT
- **THEN** the server responds with HTTP 401

#### Scenario: Invalid cloud JWT rejected

- **WHEN** a request includes `X-Cloud-JWT` header with an invalid JWT (bad signature, malformed)
- **THEN** the server responds with HTTP 401

#### Scenario: Cloud JWT not present falls through to other auth

- **WHEN** a request does not include `X-Cloud-JWT` header
- **THEN** the auth chain proceeds to check local/SSO auth as normal

#### Scenario: JWKS caching

- **WHEN** the server validates a cloud JWT
- **AND** the JWKS has been fetched within the TTL period
- **THEN** the cached JWKS is used without re-fetching

#### Scenario: Audit logging with cloud identity

- **WHEN** a task is created via a cloud-proxied request with `X-Cloud-JWT`
- **THEN** the audit metadata records the user identity from the JWT's `sub` claim as the creator

### Requirement: Cloud-trusted auth only via tunnel

The `X-Cloud-JWT` header SHALL only be honored for requests arriving through the cloud tunnel proxy handler. Direct HTTP requests to the server with `X-Cloud-JWT` SHALL ignore the header and fall through to normal auth.

This prevents a malicious local network user from forging the header on direct API calls.

#### Scenario: Direct request with X-Cloud-JWT ignored

- **WHEN** a direct HTTP request (not from the proxy handler) includes `X-Cloud-JWT`
- **THEN** the header is ignored
- **AND** the auth chain proceeds to check local/SSO auth as normal

#### Scenario: Proxy request with X-Cloud-JWT honored

- **WHEN** a request from the cloud tunnel proxy handler includes `X-Cloud-JWT`
- **THEN** the header is validated and used for authentication
