## MODIFIED Requirements

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

#### Scenario: Connected state with subscription expiry
- **WHEN** cloud credentials exist with status "connected" AND the status response includes a `subscription.expires_at` field
- **THEN** the page SHALL display the subscription expiry date below the connected status indicator
- **THEN** the expiry SHALL be formatted as a human-readable date (e.g. "Subscription expires 15 Apr 2026")

#### Scenario: Connected state with inactive subscription
- **WHEN** cloud credentials exist with status "connected" AND the status response includes `subscription.active === false`
- **THEN** the page SHALL display a warning indicator alongside the subscription expiry
- **THEN** the page SHALL show the message "Your Errand Cloud subscription has expired. Endpoint registration is unavailable."

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

#### Scenario: Endpoint registration error
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured AND the status response includes `endpoint_error`
- **THEN** the page SHALL display a toast notification on load with the error message (e.g. "Endpoint registration failed: Active subscription required")
- **THEN** the page SHALL display an inline error message in the Cloud Endpoints section instead of "Endpoints are being registered..."
- **THEN** the inline error SHALL include the `endpoint_error.detail` from the status response
- **THEN** the "Endpoints are being registered..." message SHALL NOT be shown when `endpoint_error` is present

#### Scenario: No endpoints yet (no error)
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured AND no endpoints are registered AND no `endpoint_error` is present
- **THEN** the page SHALL display a "Registering endpoints..." loading state

### Requirement: Cloud status API endpoint
The backend SHALL expose `GET /api/cloud/status` requiring the `admin` role. The endpoint returns the current cloud connection state for the frontend.

#### Scenario: Connected
- **WHEN** cloud credentials exist with status "connected" and the WebSocket client is active
- **THEN** the response SHALL be `{"status": "connected", "tenant_id": "...", "endpoints": [...], "slack_configured": bool}`
- **THEN** the response SHALL include `"subscription": {"active": bool, "expires_at": str | null}` when the cloud service subscription API responds successfully
- **THEN** the response SHALL include `"endpoint_error": {"detail": str}` when a registration failure is stored in the `cloud_endpoint_error` Setting

#### Scenario: Disconnected
- **WHEN** no cloud credentials exist
- **THEN** the response SHALL be `{"status": "not_configured"}`

#### Scenario: Error
- **WHEN** cloud credentials exist with status "error"
- **THEN** the response SHALL be `{"status": "error", "detail": "..."}`
