## MODIFIED Requirements

### Requirement: Automatic endpoint registration with errand-cloud
The backend SHALL automatically register webhook endpoints with errand-cloud when both cloud credentials and Slack credentials are active.

#### Scenario: Cloud connected, Slack already enabled
- **WHEN** a user completes cloud authentication and Slack credentials exist with status "connected"
- **THEN** the backend SHALL call `POST /api/endpoints` on the cloud service with `{integration: "slack", label: "<instance-label>", signing_secret: "<slack-signing-secret>"}`
- **THEN** the backend SHALL store the returned endpoint URLs in the `cloud_endpoints` setting
- **THEN** the Authorization header SHALL use the cloud access token

#### Scenario: Slack enabled, cloud already connected
- **WHEN** a user saves Slack credentials and cloud PlatformCredential exists with status "connected"
- **THEN** the backend SHALL register cloud endpoints (same as above)

#### Scenario: Idempotent registration
- **WHEN** cloud endpoints for Slack already exist in the `cloud_endpoints` setting
- **THEN** the backend SHALL check `GET /api/endpoints?integration=slack` on the cloud service
- **THEN** if endpoints exist and are active, the backend SHALL NOT create duplicates
- **THEN** if no active endpoints exist (e.g., previously revoked), the backend SHALL create new ones

#### Scenario: Registration failure
- **WHEN** the cloud endpoint registration API call fails (network error, auth error, server error)
- **THEN** the backend SHALL log the error including the HTTP status code and response body
- **THEN** the backend SHALL store the error detail in the `cloud_endpoint_error` Setting
- **THEN** the backend SHALL NOT block the Slack credential save or cloud authentication flow
- **THEN** `GET /api/cloud/status` SHALL include `endpoint_error: {detail: "<message>"}` so the frontend can notify the user

#### Scenario: Registration succeeds after previous failure
- **WHEN** endpoint registration completes successfully
- **THEN** the backend SHALL delete the `cloud_endpoint_error` Setting if it exists

### Requirement: Endpoint cleanup on disconnect
When the user disconnects from errand-cloud, the backend SHALL revoke cloud endpoints.

#### Scenario: Disconnect revokes endpoints
- **WHEN** the user disconnects from errand-cloud via the settings page
- **THEN** the backend SHALL call `DELETE /api/endpoints?integration=slack` on the cloud service
- **THEN** the backend SHALL delete the `cloud_endpoints` setting
- **THEN** the backend SHALL delete the `cloud_endpoint_error` setting

#### Scenario: Endpoint cleanup failure
- **WHEN** the cloud endpoint revocation API call fails
- **THEN** the backend SHALL log the error but proceed with local cleanup (delete credentials and settings)
