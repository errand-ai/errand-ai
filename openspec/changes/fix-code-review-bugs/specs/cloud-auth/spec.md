## ADDED Requirements

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
