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

#### Scenario: Connected state with payment warning
- **WHEN** cloud credentials exist with status "connected" AND the status response includes `subscription.payment_warning`
- **THEN** the page SHALL display a payment warning indicator alongside the subscription expiry line
- **THEN** the indicator colour SHALL be amber/orange for retryable failures and red for final failures
- **THEN** the warning message SHALL reflect the alert type (see payment-status-display spec)

#### Scenario: Error state
- **WHEN** cloud credentials exist with status "error"
- **THEN** the page SHALL display connection status as error (red indicator) with the error detail
- **THEN** the page SHALL display a "Reconnect" button that initiates re-authentication

### Requirement: Cloud status API endpoint
The backend SHALL expose `GET /api/cloud/status` requiring the `admin` role. The endpoint returns the current cloud connection state for the frontend.

#### Scenario: Connected
- **WHEN** cloud credentials exist with status "connected" and the WebSocket client is active
- **THEN** the response SHALL be `{"status": "connected", "tenant_id": "...", "endpoints": [...], "slack_configured": bool}`
- **THEN** the response SHALL include `"subscription": {"active": bool, "expires_at": str | null}` when the cloud service subscription API responds successfully
- **THEN** the response SHALL include `"subscription.payment_warning": {alert, plan, attempt_count, next_retry_at, final_attempt}` when a `cloud_payment_warning` Setting exists
- **THEN** the response SHALL include `"endpoint_error": {"detail": str}` when a registration failure is stored in the `cloud_endpoint_error` Setting

#### Scenario: Disconnected
- **WHEN** no cloud credentials exist
- **THEN** the response SHALL be `{"status": "not_configured"}`

#### Scenario: Error
- **WHEN** cloud credentials exist with status "error"
- **THEN** the response SHALL be `{"status": "error", "detail": "..."}`
