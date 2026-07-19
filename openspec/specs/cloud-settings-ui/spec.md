## Purpose

The Cloud Service settings subpage lets an admin connect the local errand instance to Errand Cloud, view connection and subscription status (including payment warnings), and manage the webhook endpoints registered through the cloud relay.
## Requirements
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

### Requirement: Cloud endpoint URL display
The Cloud Service settings page SHALL display the cloud webhook endpoint URLs when available, including per-trigger URLs for Jira and GitHub webhook triggers.

#### Scenario: Slack endpoints visible when Slack is enabled
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured
- **THEN** the page SHALL display a "Cloud Endpoints" section listing each Slack endpoint with its integration, type, and full URL
- **THEN** each endpoint URL SHALL have a "Copy" button to copy the URL to clipboard

#### Scenario: Per-trigger Jira and GitHub URLs visible
- **WHEN** the user is connected to errand-cloud AND one or more Jira or GitHub webhook triggers exist with `cloud_webhook_url` populated
- **THEN** the "Cloud Endpoints" section SHALL list each trigger's URL alongside the trigger's name and source (jira/github)
- **THEN** each URL SHALL have a "Copy" button to copy the URL to clipboard

#### Scenario: Trigger exists but cloud not connected
- **WHEN** a Jira or GitHub webhook trigger exists but `cloud_webhook_url` is null because the user is not connected to errand-cloud
- **THEN** the trigger's row in the "Cloud Endpoints" section SHALL display "Cloud not connected" in place of the URL
- **THEN** no "Copy" button SHALL be shown for that row

#### Scenario: Trigger exists but registration failed
- **WHEN** a Jira or GitHub webhook trigger exists, the user is connected to errand-cloud, but `cloud_webhook_url` is null because the most recent registration attempt failed
- **THEN** the trigger's row SHALL display "Registration failed — re-save trigger to retry"
- The per-row text SHALL NOT include `endpoint_error.detail` — that Setting is global (shared with Slack registration and other triggers) and would mis-attribute unrelated failures to the wrong trigger row. The detail SHALL be surfaced once at section level via the persistent endpoint-error banner instead.

#### Scenario: Endpoints hidden when no integrations are configured
- **WHEN** the user is connected to errand-cloud AND no Slack credentials, Jira triggers, or GitHub triggers exist
- **THEN** the "Cloud Endpoints" section SHALL NOT be displayed
- **THEN** a message SHALL indicate "Configure Slack, Jira, or GitHub in Integrations to see cloud webhook endpoints"

#### Scenario: Endpoint registration error
- **WHEN** the user is connected to errand-cloud AND the status response includes `endpoint_error`
- **THEN** the page SHALL display a toast notification on load with the error message (e.g. "Endpoint registration failed: Active subscription required")
- **THEN** the page SHALL display an inline error message in the Cloud Endpoints section for any endpoint that failed to register
- **THEN** the inline error SHALL include the `endpoint_error.detail` from the status response

#### Scenario: No Slack endpoints yet (no error)
- **WHEN** the user is connected to errand-cloud AND Slack credentials are configured AND no Slack endpoints are registered AND no `endpoint_error` is present
- **THEN** the page SHALL display a "Registering endpoints..." loading state for the Slack rows

### Requirement: Cloud status API endpoint
The backend SHALL expose `GET /api/cloud/status` requiring the `admin` role. The endpoint returns the current cloud connection state for the frontend.

#### Scenario: Connected
- **WHEN** cloud credentials exist with status "connected" and the WebSocket client is active
- **THEN** the response SHALL be `{"status": "connected", "tenant_id": "...", "endpoints": [...], "slack_configured": bool}`
- **THEN** the response SHALL include `"subscription": {"active": bool, "expires_at": str | null}` when the cloud service subscription API responds successfully
- **THEN** the `subscription` object SHALL include a nested `payment_warning` field `{alert, plan, attempt_count, next_retry_at, final_attempt}` when a `cloud_payment_warning` Setting exists
- **THEN** the response SHALL include `"endpoint_error": {"detail": str}` when a registration failure is stored in the `cloud_endpoint_error` Setting

#### Scenario: Disconnected
- **WHEN** no cloud credentials exist
- **THEN** the response SHALL be `{"status": "not_configured"}`

#### Scenario: Error
- **WHEN** cloud credentials exist with status "error"
- **THEN** the response SHALL be `{"status": "error", "detail": "..."}`

