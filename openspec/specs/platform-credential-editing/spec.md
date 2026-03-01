## Purpose

Field-level classification and partial update support for platform credentials, allowing configuration fields to be edited post-connection without re-verification.

## Requirements

### Requirement: Editable field classification in credential schema
Each field in a platform's `credential_schema` MAY include an `"editable": true` property to indicate the field can be updated post-connection without requiring re-verification or disconnection. Fields without `editable` or with `editable: false` are connection fields that require disconnect/reconnect to change. Platforms SHALL mark configuration-only fields as editable (e.g., `email_profile`, `poll_interval`, `authorized_recipients` for the email platform).

#### Scenario: Email platform marks configuration fields as editable
- **WHEN** the email platform's `credential_schema` is inspected
- **THEN** the `email_profile`, `poll_interval`, and `authorized_recipients` fields have `"editable": true`
- **AND** the `imap_host`, `imap_port`, `smtp_host`, `smtp_port`, `security`, `username`, and `password` fields do NOT have `"editable": true`

#### Scenario: Platform with no editable fields
- **WHEN** a platform's `credential_schema` has no fields with `"editable": true`
- **THEN** no edit button is shown for that platform when connected

### Requirement: Patch platform credentials API
The backend SHALL expose `PATCH /api/platforms/{platform_id}/credentials` requiring the `admin` role. The endpoint SHALL accept a partial JSON object containing only the fields to update. The endpoint SHALL decrypt the existing credentials, merge the provided fields, re-encrypt, and store the updated credentials. The endpoint SHALL only accept fields that are marked `editable: true` in the platform's credential schema; any non-editable field in the request SHALL be rejected with HTTP 400. The endpoint SHALL NOT trigger credential re-verification. The endpoint SHALL return the updated platform status.

#### Scenario: Update editable field
- **WHEN** an admin sends `PATCH /api/platforms/email/credentials` with `{"poll_interval": "120"}`
- **THEN** the stored credentials are updated with the new poll_interval value, other fields remain unchanged, and the response includes the platform status

#### Scenario: Update multiple editable fields
- **WHEN** an admin sends `PATCH /api/platforms/email/credentials` with `{"email_profile": "new-uuid", "authorized_recipients": "user@example.com"}`
- **THEN** both fields are updated in the stored credentials and other fields remain unchanged

#### Scenario: Reject non-editable field
- **WHEN** an admin sends `PATCH /api/platforms/email/credentials` with `{"password": "new-password"}`
- **THEN** the response is HTTP 400 with an error indicating the field is not editable

#### Scenario: No credentials to patch
- **WHEN** an admin sends `PATCH /api/platforms/email/credentials` and no credentials are stored
- **THEN** the response is HTTP 400 with an error indicating no credentials are configured

#### Scenario: Unknown platform
- **WHEN** an admin sends `PATCH /api/platforms/unknown/credentials`
- **THEN** the response is HTTP 404

### Requirement: Return editable field values in GET response
The `GET /api/platforms/{platform_id}/credentials` endpoint SHALL include a `field_values` dict in the response containing the current values of fields marked `editable: true` in the platform's credential schema. Sensitive fields (those without `editable: true`) SHALL NOT be included in `field_values`. If no credentials are stored, `field_values` SHALL be an empty dict.

#### Scenario: GET returns editable field values
- **WHEN** an admin requests `GET /api/platforms/email/credentials` and email credentials are stored
- **THEN** the response includes `field_values` with keys `email_profile`, `poll_interval`, and `authorized_recipients` and their current values
- **AND** the response does NOT include `password`, `username`, `imap_host`, or other non-editable fields in `field_values`

#### Scenario: GET with no credentials returns empty field_values
- **WHEN** an admin requests `GET /api/platforms/email/credentials` and no credentials are stored
- **THEN** the response includes `field_values: {}`
