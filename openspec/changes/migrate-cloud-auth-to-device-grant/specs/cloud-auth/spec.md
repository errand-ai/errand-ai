## MODIFIED Requirements

### Requirement: Cloud OAuth login initiation
The backend SHALL expose `POST /api/cloud/auth/device` requiring the `admin` role. The endpoint SHALL begin an OAuth 2.0 device authorization grant (RFC 8628) against errand-cloud and SHALL NOT send errand-cloud a callback URL of any kind.

The previous requirement described a PKCE authorization-code flow conducted directly against Keycloak. That was never what the implementation did — it generated no PKCE parameters and redirected to errand-cloud's `/auth/tenant/login`, passing this instance's own callback as `redirect_uri`. errand-cloud now refuses a `redirect_uri` outside its own origin, because a caller-supplied one meant the authorization code could be delivered to an attacker. The device grant has no such parameter.

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

#### Scenario: A second grant supersedes the first
- **WHEN** an admin begins a device authorization while another is pending
- **THEN** the backend SHALL abandon the pending grant and begin a new one

### Requirement: Cloud OAuth callback
The backend SHALL NOT expose a redirect callback for cloud authentication. `GET /api/cloud/auth/callback` and the `cloud_auth_state` nonce SHALL be removed.

Nothing redirects to this instance once the device grant is in use, so a callback endpoint and its CSRF nonce protect nothing and only enlarge the authenticated-adjacent surface.

#### Scenario: The callback is gone
- **WHEN** a request is made to `GET /api/cloud/auth/callback`
- **THEN** the backend SHALL NOT process an authorization code

## ADDED Requirements

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
