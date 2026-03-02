## Requirements

### Requirement: Subscription status fetched from cloud service
The backend SHALL fetch subscription status from the cloud service when building the `GET /api/cloud/status` response.

#### Scenario: Subscription info available
- **WHEN** cloud credentials exist with status "connected" and `GET /api/subscription` on the cloud service returns successfully
- **THEN** the cloud status response SHALL include a `subscription` object with `active` (bool) and `expires_at` (ISO 8601 string or null)

#### Scenario: Subscription endpoint unavailable
- **WHEN** the cloud service `GET /api/subscription` call fails (network error, 404, or any non-2xx response)
- **THEN** the cloud status response SHALL omit the `subscription` field entirely
- **THEN** the failure SHALL be logged at DEBUG level and SHALL NOT affect the rest of the status response

#### Scenario: Not connected
- **WHEN** cloud credentials do not exist or status is not "connected"
- **THEN** the backend SHALL NOT call `GET /api/subscription`
- **THEN** the `subscription` field SHALL be absent from the response

### Requirement: Endpoint registration error stored and exposed
The backend SHALL persist endpoint registration failures so they can be surfaced to the frontend on subsequent page loads.

#### Scenario: Registration fails
- **WHEN** `POST /api/endpoints` on the cloud service returns a non-2xx response
- **THEN** the backend SHALL store `{detail: "<error message>", timestamp: <unix float>}` in the `cloud_endpoint_error` Setting
- **THEN** `GET /api/cloud/status` SHALL include `endpoint_error: {detail: "<error message>"}` in its response

#### Scenario: Registration succeeds after previous failure
- **WHEN** endpoint registration completes successfully and a `cloud_endpoint_error` Setting exists
- **THEN** the backend SHALL delete the `cloud_endpoint_error` Setting

#### Scenario: Disconnect clears endpoint error
- **WHEN** the user disconnects from errand-cloud
- **THEN** the backend SHALL delete the `cloud_endpoint_error` Setting as part of cleanup
