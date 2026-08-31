## ADDED Requirements

### Requirement: OIDC authorization requests carry a validated `state` parameter

The backend SHALL include a `state` parameter in every OIDC authorization request, and SHALL reject any callback whose `state` is absent, malformed, expired, or does not match the one it issued.

The value SHALL be unguessable, SHALL be bound to the browser that initiated the flow, and SHALL expire. RFC 6749 §10.12 requires this: without it, an attacker can complete an authorization flow the user's browser never began, and have the victim's session bound to the attacker's identity.

A callback failing validation SHALL be rejected outright. It SHALL NOT fall back to accepting the callback with a warning — an attacker who omits `state` would then face no check at all, which is the attack.

#### Scenario: Authorization request includes state

- **WHEN** a user begins login and the backend redirects to the OIDC provider
- **THEN** the authorization URL includes a `state` parameter

#### Scenario: Matching state is accepted

- **WHEN** the provider returns to the callback with the `state` the backend issued, unexpired
- **THEN** the flow proceeds to token exchange

#### Scenario: Missing state is rejected

- **WHEN** a callback arrives with no `state` parameter
- **THEN** the request is rejected and no token exchange occurs

#### Scenario: Mismatched state is rejected

- **WHEN** a callback arrives with a `state` the backend did not issue
- **THEN** the request is rejected and no token exchange occurs

#### Scenario: Expired state is rejected

- **WHEN** a callback arrives with a well-formed `state` whose expiry has passed
- **THEN** the request is rejected and no token exchange occurs

#### Scenario: A rejected callback does not authenticate

- **WHEN** any of the rejection cases above occurs
- **THEN** no session is established and no tokens are returned to the browser

### Requirement: Cross-origin access is restricted to configured origins

The backend SHALL restrict cross-origin requests to an explicitly configured set of origins. It SHALL NOT allow all origins by default.

The default SHALL permit the deployment's own origin, so a standard single-origin deployment — where the backend serves the frontend — requires no configuration.

Credentialed cross-origin requests SHALL remain disabled unless deliberately enabled alongside an origin allowlist. errand authenticates with Bearer tokens and sets no cookies; a wildcard is therefore not currently exploitable, but it becomes so the moment cookie authentication is introduced. The restriction exists to remove that latent hazard, not to fix a live exploit.

#### Scenario: Same-origin request succeeds by default

- **WHEN** the frontend served by the backend calls the API
- **THEN** the request succeeds without any origin configuration

#### Scenario: Unconfigured origin is refused

- **WHEN** a page on an origin not in the configured set makes a cross-origin API request
- **THEN** the response does not grant that origin access

#### Scenario: Configured origin is permitted

- **WHEN** an origin has been added to the configured set and makes a cross-origin API request
- **THEN** the response grants that origin access

#### Scenario: Wildcard is not the default

- **WHEN** the deployment has no CORS configuration
- **THEN** the allowed origins do not include `*`
