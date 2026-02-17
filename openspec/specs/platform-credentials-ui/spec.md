## Purpose

Frontend UI for managing platform credentials — viewing connection status, configuring credentials, and verifying/disconnecting platforms.

## Requirements

### Requirement: Platform settings page
The frontend SHALL provide a "Platforms" page accessible from the settings navigation. The page SHALL display a card for each registered platform showing its label, capabilities, and connection status. The page SHALL be accessible only to users with the `admin` role.

#### Scenario: Admin views platform settings
- **WHEN** an admin navigates to the Platforms settings page
- **THEN** a card is displayed for each registered platform with its name, capabilities as tags, and connection status (connected/disconnected)

#### Scenario: Non-admin cannot access
- **WHEN** a non-admin user attempts to navigate to the Platforms settings page
- **THEN** the page is not shown in navigation and direct access redirects to the main view

### Requirement: Platform credential configuration form
Each platform card SHALL have a "Configure" button that expands an inline form. The form fields SHALL be dynamically rendered from the platform's `credential_schema` (fetched from `GET /api/platforms`). All credential fields SHALL be rendered as password-type inputs with a toggle to reveal the value. The form SHALL have "Test & Save" and "Cancel" buttons.

#### Scenario: Configure Twitter credentials
- **WHEN** an admin clicks "Configure" on the Twitter card
- **THEN** a form appears with masked input fields for API Key, API Secret, Access Token, and Access Secret (as defined by Twitter's credential_schema)

#### Scenario: Save credentials
- **WHEN** an admin fills in all credential fields and clicks "Test & Save"
- **THEN** the frontend sends `PUT /api/platforms/twitter/credentials` with the field values and displays the result (connected or error message)

#### Scenario: Cancel editing
- **WHEN** an admin clicks "Cancel" on an open credential form
- **THEN** the form collapses and no changes are saved

### Requirement: Platform connection status display
Each platform card SHALL display the current connection status: a green indicator with "Connected" and the last verified timestamp for connected platforms, or a grey indicator with "Not configured" for disconnected platforms, or a red indicator with "Error" for platforms with failed verification.

#### Scenario: Connected platform
- **WHEN** a platform has status "connected" with `last_verified_at` of 2 hours ago
- **THEN** the card shows a green indicator, "Connected", and "Verified 2 hours ago"

#### Scenario: Disconnected platform
- **WHEN** a platform has status "disconnected"
- **THEN** the card shows a grey indicator and "Not configured"

### Requirement: Disconnect platform action
Each connected platform card SHALL have a "Disconnect" button that, when clicked, shows a confirmation dialog and then calls `DELETE /api/platforms/{platform_id}/credentials`. The card SHALL update to show "Not configured" after successful disconnection.

#### Scenario: Disconnect a platform
- **WHEN** an admin clicks "Disconnect" on a connected Twitter card and confirms
- **THEN** the credentials are deleted and the card updates to show "Not configured"

### Requirement: Re-verify platform action
Each connected platform card SHALL have a "Re-verify" button that calls `POST /api/platforms/{platform_id}/credentials/verify` and updates the displayed status based on the result.

#### Scenario: Re-verify succeeds
- **WHEN** an admin clicks "Re-verify" on a connected platform
- **THEN** the last_verified_at timestamp updates and status remains "Connected"

#### Scenario: Re-verify fails
- **WHEN** an admin clicks "Re-verify" and the credentials are no longer valid
- **THEN** the status changes to "Error" with the failure reason displayed
