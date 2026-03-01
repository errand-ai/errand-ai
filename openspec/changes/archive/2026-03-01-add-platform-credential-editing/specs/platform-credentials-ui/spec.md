## ADDED Requirements

### Requirement: Edit button for connected platforms with editable fields
Each connected platform card SHALL display an "Edit" button if the platform's credential schema contains at least one field with `editable: true`. Clicking "Edit" SHALL toggle an inline form showing only the editable fields, pre-populated with current values from the GET credentials response. The "Edit" button SHALL NOT appear for platforms with no editable fields.

#### Scenario: Connected email platform shows Edit button
- **WHEN** an admin views the Platforms settings page and the email platform is connected
- **THEN** the email card shows "Edit", "Verify", and "Disconnect" buttons

#### Scenario: Connected platform with no editable fields
- **WHEN** an admin views the Platforms settings page and a platform with no editable schema fields is connected
- **THEN** the platform card shows "Verify" and "Disconnect" buttons but no "Edit" button

### Requirement: Inline edit form for editable fields
When the "Edit" button is clicked on a connected platform card, an inline form SHALL appear showing only fields with `editable: true` from the credential schema. Each field SHALL be pre-populated with its current value from the `field_values` in the GET credentials response. The form SHALL have "Save" and "Cancel" buttons. Clicking "Save" SHALL send a `PATCH /api/platforms/{platform_id}/credentials` request with the changed field values. Clicking "Cancel" SHALL hide the form without making changes.

#### Scenario: Edit email configuration fields
- **WHEN** an admin clicks "Edit" on the connected email card
- **THEN** a form appears with the `email_profile`, `poll_interval`, and `authorized_recipients` fields, pre-populated with their current values
- **AND** the form does NOT show connection fields like `imap_host`, `smtp_host`, `username`, or `password`

#### Scenario: Save edited fields
- **WHEN** an admin changes the `poll_interval` field to "120" and clicks "Save"
- **THEN** a PATCH request is sent with `{"poll_interval": "120"}` and the form closes on success with a toast confirmation

#### Scenario: Cancel edit
- **WHEN** an admin opens the edit form and clicks "Cancel"
- **THEN** the form closes and no PATCH request is sent

### Requirement: Edit form uses credential form component
The inline edit form SHALL reuse the `PlatformCredentialForm` component with an `editableOnly` mode that filters the schema to show only `editable: true` fields and accepts `initialValues` for pre-population. The form SHALL emit a `save` event with only the changed field values.

#### Scenario: Form renders only editable fields
- **WHEN** `PlatformCredentialForm` is rendered in `editableOnly` mode for the email platform
- **THEN** only `email_profile`, `poll_interval`, and `authorized_recipients` fields are rendered
- **AND** connection fields are excluded from the form
