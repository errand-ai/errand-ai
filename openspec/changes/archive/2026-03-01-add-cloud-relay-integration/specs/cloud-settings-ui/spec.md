## ADDED Requirements

### Requirement: Cloud Service settings subpage
The frontend SHALL provide a "Cloud Service" settings subpage at `/settings/cloud` for managing the errand-cloud connection.

#### Scenario: Not connected state
- **WHEN** the user navigates to `/settings/cloud` and no cloud credentials exist
- **THEN** the page SHALL display a description of the cloud service: "Connect your instance to Errand Cloud to receive webhooks without configuring port forwarding"
- **THEN** the page SHALL display a "Connect to Errand Cloud" button
- **THEN** clicking the button SHALL navigate to `/api/cloud/auth/login` (initiating the OAuth flow)

#### Scenario: Connected state
- **WHEN** the user navigates to `/settings/cloud` and cloud credentials exist with status "connected"
- **THEN** the page SHALL display connection status as connected (green indicator)
- **THEN** the page SHALL display a "Disconnect" button
- **THEN** clicking "Disconnect" SHALL call `POST /api/cloud/auth/disconnect` and refresh the page state

#### Scenario: Error state
- **WHEN** cloud credentials exist with status "error"
- **THEN** the page SHALL display connection status as error (red indicator) with the error detail
- **THEN** the page SHALL display a "Reconnect" button that initiates re-authentication

### Requirement: Cloud endpoint URL display
The Cloud Service settings page SHALL display the cloud webhook endpoint URLs when available.

#### Scenario: Slack endpoints visible when Slack is enabled
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured
- **THEN** the page SHALL display a "Cloud Endpoints" section listing each endpoint with its integration, type, and full URL
- **THEN** each endpoint URL SHALL have a "Copy" button to copy the URL to clipboard

#### Scenario: Endpoints hidden when Slack is not enabled
- **WHEN** the user is connected to errand-cloud AND no Slack credentials are configured
- **THEN** the "Cloud Endpoints" section SHALL NOT be displayed
- **THEN** a message SHALL indicate "Enable Slack in Integrations to configure cloud webhook endpoints"

#### Scenario: No endpoints yet
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured BUT no cloud endpoints have been registered yet
- **THEN** the page SHALL display a "Registering endpoints..." loading state or a "Register Endpoints" button

### Requirement: Cloud status API endpoint
The backend SHALL expose `GET /api/cloud/status` requiring the `admin` role. The endpoint returns the current cloud connection state for the frontend.

#### Scenario: Connected
- **WHEN** cloud credentials exist with status "connected" and the WebSocket client is active
- **THEN** the response SHALL be `{"status": "connected", "tenant_id": "...", "endpoints": [...]}`

#### Scenario: Disconnected
- **WHEN** no cloud credentials exist
- **THEN** the response SHALL be `{"status": "not_configured"}`

#### Scenario: Error
- **WHEN** cloud credentials exist with status "error"
- **THEN** the response SHALL be `{"status": "error", "detail": "..."}`
