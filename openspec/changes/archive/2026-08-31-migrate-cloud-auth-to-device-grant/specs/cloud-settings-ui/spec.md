## MODIFIED Requirements

### Requirement: Cloud Service settings subpage
The frontend SHALL provide a "Cloud Service" settings subpage at `/settings/cloud` for managing the errand-cloud connection.

The not-connected scenario previously said the Connect button navigates to `/api/cloud/auth/login`, which no longer exists — that endpoint returned a redirect URL for a popup, and the redirect flow has been replaced by the device authorization grant. The button now starts a grant in place.

#### Scenario: Not connected state
- **WHEN** the user navigates to `/settings/cloud` and no cloud credentials exist
- **THEN** the page SHALL display a description of the cloud service: "Connect your instance to Errand Cloud to receive webhooks without configuring port forwarding"
- **THEN** the page SHALL display a "Connect to Errand Cloud" button
- **THEN** clicking the button SHALL send `POST /api/cloud/auth/device`, beginning a device authorization grant
- **THEN** the page SHALL NOT open a popup window

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
