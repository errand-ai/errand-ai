## MODIFIED Requirements

### Requirement: Get platform credentials status API
The backend SHALL expose `GET /api/platforms/{platform_id}/credentials` requiring the `admin` role. The endpoint SHALL return the credential status (connected/disconnected/error), last_verified_at, the credential field names that are configured (but never the actual values), and a `field_values` dict containing the current values of fields marked `editable: true` in the platform's credential schema. If no credentials are stored, it SHALL return status "disconnected" with empty `field_values`.

#### Scenario: Credentials configured
- **WHEN** an admin requests `GET /api/platforms/twitter/credentials` and Twitter credentials exist
- **THEN** the response includes `{"platform_id": "twitter", "status": "connected", "last_verified_at": "...", "configured_fields": ["api_key", "api_secret", "access_token", "access_secret"], "field_values": {}}`

#### Scenario: Credentials configured with editable fields
- **WHEN** an admin requests `GET /api/platforms/email/credentials` and email credentials exist with `poll_interval: "120"`
- **THEN** the response includes `field_values` containing `{"email_profile": "...", "poll_interval": "120", "authorized_recipients": "..."}`

#### Scenario: No credentials configured
- **WHEN** an admin requests `GET /api/platforms/twitter/credentials` and no Twitter credentials exist
- **THEN** the response is `{"platform_id": "twitter", "status": "disconnected", "last_verified_at": null, "configured_fields": [], "field_values": {}}`
