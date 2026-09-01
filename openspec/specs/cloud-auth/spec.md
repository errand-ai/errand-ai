## Purpose

OAuth 2.0 device authorization grant (RFC 8628) between the backend and errand-cloud, including credential persistence, offline token refresh, and SSRF-safe JWT validation. The backend sends errand-cloud no callback URL, so there is nothing for the cloud to verify and nothing an attacker could substitute.
## Requirements
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

### Requirement: Cloud device authorization initiation
The backend SHALL expose `POST /api/cloud/auth/device` requiring the `admin` role. The endpoint SHALL begin an OAuth 2.0 device authorization grant (RFC 8628) against errand-cloud and SHALL NOT send errand-cloud a callback URL of any kind.

errand-cloud refuses a `redirect_uri` outside its own origin, because a caller-supplied one meant the authorization code could be delivered to an attacker. The device grant has no such parameter.

#### Scenario: Grant initiated
- **WHEN** an admin sends `POST /api/cloud/auth/device`
- **THEN** the backend SHALL request a device authorization from errand-cloud
- **AND** it SHALL return the user-facing verification code, the verification URI, a completion URI carrying the code, and the grant's expiry
- **AND** it SHALL NOT return or store the device code in any client-visible response

#### Scenario: No callback is offered
- **WHEN** the backend begins a device authorization
- **THEN** the request SHALL contain no `redirect_uri` or equivalent callback parameter

#### Scenario: Cloud not configured
- **WHEN** an admin sends `POST /api/cloud/auth/device` and the cloud service URL is not available
- **THEN** the backend SHALL return HTTP 503 with detail "Cloud service not configured"

#### Scenario: Malformed device authorization
- **WHEN** errand-cloud's response omits the device code, the user code or the verification URI, or carries an unusable expiry
- **THEN** the backend SHALL return HTTP 502 and SHALL NOT start polling

#### Scenario: A second grant supersedes the first
- **WHEN** an admin begins a device authorization while another is pending
- **THEN** the backend SHALL abandon the pending grant and begin a new one
- **AND** the abandoned grant SHALL NOT store credentials or report an outcome afterwards

### Requirement: No cloud redirect callback
The backend SHALL NOT expose a redirect callback for cloud authentication.

Nothing redirects to this instance once the device grant is in use, so a callback endpoint and its CSRF nonce protect nothing and only enlarge the authenticated-adjacent surface.

#### Scenario: The callback is gone
- **WHEN** a request is made to `GET /api/cloud/auth/callback`
- **THEN** the backend SHALL NOT process an authorization code

### Requirement: Device grant completion
The backend SHALL poll errand-cloud for the outcome of a pending device authorization and SHALL store credentials on success exactly as the previous flow did.

Polling happens server-side. The device code is a bearer credential — whoever holds it collects the tokens — so it SHALL NOT be exposed to the browser.

#### Scenario: User authorises the grant
- **WHEN** the user completes verification and the backend's next poll returns tokens
- **THEN** the backend SHALL extract the `sub` claim from the access token as the tenant_id
- **AND** it SHALL encrypt and store `access_token`, `refresh_token`, `token_expiry` and `tenant_id` as a PlatformCredential with `platform_id = "cloud"` and `status = "connected"`
- **AND** it SHALL start the cloud WebSocket client background task
- **AND** it SHALL trigger cloud endpoint registration if Slack credentials are already configured

#### Scenario: Authorization still pending
- **WHEN** a poll reports that the user has not yet authorised
- **THEN** the backend SHALL keep polling until the grant expires
- **AND** it SHALL NOT modify stored credentials

#### Scenario: Polling respects the advertised interval
- **WHEN** errand-cloud advertises a minimum polling interval
- **THEN** the backend SHALL wait at least that interval between polls
- **AND** on being told to slow down it SHALL increase its interval rather than retry at the same rate

#### Scenario: Rate limiting is not retried harder
- **WHEN** errand-cloud answers a poll with HTTP 429
- **THEN** the backend SHALL treat it as an error and stop, rather than tightening its polling loop

#### Scenario: User refuses
- **WHEN** a poll reports that the user refused the request
- **THEN** the backend SHALL stop polling
- **AND** it SHALL NOT modify stored credentials

#### Scenario: Grant expires
- **WHEN** the grant expires before the user authorises it
- **THEN** the backend SHALL stop polling
- **AND** the pending grant SHALL be reported as expired

#### Scenario: Polling stops with the grant
- **WHEN** a grant reaches any terminal outcome
- **THEN** no polling task for it SHALL remain running

### Requirement: Device grant status
The backend SHALL expose `GET /api/cloud/auth/device/status` requiring the `admin` role, reporting the state of the current grant so the UI can show progress without holding a request open.

#### Scenario: Status while pending
- **WHEN** an admin requests the status of a pending grant
- **THEN** the backend SHALL report that it is pending
- **AND** it SHALL include the verification code and URI so the page can be reloaded without losing them

#### Scenario: Status after completion
- **WHEN** an admin requests the status after the grant completed
- **THEN** the backend SHALL report that the instance is connected

#### Scenario: Status of a failed grant
- **WHEN** a grant was refused, expired, or errored
- **THEN** the backend SHALL report that outcome distinctly from "pending"

#### Scenario: No grant in progress
- **WHEN** an admin requests the status with no grant started
- **THEN** the backend SHALL report that none is in progress

### Requirement: Device grant is presented in the page
The cloud settings page SHALL present the verification code and link in the page itself rather than opening a popup, and SHALL reflect the grant's outcome without the user reloading.

A popup carried the redirect flow's browser round trip. The device grant has no round trip to carry, and a popup would be a worse place to display a code the user must read or click.

#### Scenario: Code is shown
- **WHEN** an admin starts a device authorization from the cloud settings page
- **THEN** the page SHALL display the verification code and a link to the verification URI

#### Scenario: Outcome is reflected
- **WHEN** the grant completes, is refused, or expires
- **THEN** the page SHALL show the outcome without a manual reload

#### Scenario: A stale status response is ignored
- **WHEN** a status poll completes after a later one has already reported an outcome
- **THEN** the page SHALL ignore the stale response

#### Scenario: The session dies mid-grant
- **WHEN** a status poll is rejected as unauthorized
- **THEN** the page SHALL stop polling and report the failure rather than remain pending indefinitely

