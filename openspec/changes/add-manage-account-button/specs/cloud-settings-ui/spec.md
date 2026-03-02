## MODIFIED Requirements

### Requirement: Manage Account link in connected state
The Cloud Service settings page SHALL display a "Manage Account" link when connected to Errand Cloud.

#### Scenario: Manage Account button visible when connected
- **WHEN** the user is on `/settings/cloud` and the cloud status is "connected"
- **THEN** the page SHALL display a "Manage Account" link styled as a button
- **THEN** clicking the link SHALL open `https://errand.cloud` in a new browser tab
- **THEN** the link SHALL include `rel="noopener noreferrer"` for security

#### Scenario: Manage Account button not visible when not connected
- **WHEN** the cloud status is "not_configured" or "error"
- **THEN** the "Manage Account" link SHALL NOT be displayed
