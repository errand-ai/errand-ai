## ADDED Requirements

### Requirement: Payment warning stored from subscription alert
The backend SHALL store payment alert data in the Settings table under the key `cloud_payment_warning` when a `subscription_alert` message is received via Valkey pubsub.

#### Scenario: Payment failed alert received
- **WHEN** the pubsub loop receives a message on `tenant:{id}:notify` with `{"type": "subscription_alert", "alert": "payment_failed", ...}`
- **THEN** the backend SHALL store the alert payload as a JSON object in the `cloud_payment_warning` Setting
- **THEN** the stored object SHALL include `alert`, `plan`, `attempt_count`, `next_retry_at`, and `final_attempt` fields from the message

#### Scenario: Payment succeeded clears warning
- **WHEN** the pubsub loop receives a `subscription_alert` message with `"alert": "payment_succeeded"`
- **THEN** the backend SHALL delete the `cloud_payment_warning` Setting if it exists

#### Scenario: Non-alert pubsub messages unaffected
- **WHEN** the pubsub loop receives a message that does not have `"type": "subscription_alert"`
- **THEN** the message SHALL be handled by the existing webhook drain logic as before

### Requirement: Payment warning exposed in cloud status API
The `GET /api/cloud/status` endpoint SHALL include payment warning data in the `subscription` object when a `cloud_payment_warning` Setting exists.

#### Scenario: Payment warning present
- **WHEN** a `cloud_payment_warning` Setting exists AND cloud credentials are connected
- **THEN** the response `subscription` object SHALL include a `payment_warning` field containing `{alert, plan, attempt_count, next_retry_at, final_attempt}`

#### Scenario: No payment warning
- **WHEN** no `cloud_payment_warning` Setting exists
- **THEN** the response `subscription` object SHALL NOT include a `payment_warning` field

#### Scenario: Disconnect clears payment warning
- **WHEN** the user disconnects from errand-cloud
- **THEN** the backend SHALL delete the `cloud_payment_warning` Setting as part of cleanup

### Requirement: Payment warning displayed in Cloud Settings UI
The Cloud Service settings page SHALL display a payment warning indicator when `payment_warning` is present in the status response.

#### Scenario: Payment failed with retry
- **WHEN** the status response includes `subscription.payment_warning` with `alert: "payment_failed"` and `final_attempt: false`
- **THEN** the page SHALL display an amber/orange warning indicator next to the subscription expiry line
- **THEN** the warning message SHALL read "Payment failed — retrying {next_retry_at formatted as date}"

#### Scenario: Payment failed final attempt
- **WHEN** the status response includes `subscription.payment_warning` with `alert: "payment_failed"` and `final_attempt: true`
- **THEN** the page SHALL display a red warning indicator
- **THEN** the warning message SHALL read "Payment failed — subscription expired"

#### Scenario: No payment warning
- **WHEN** the status response does not include `subscription.payment_warning`
- **THEN** no payment warning indicator SHALL be displayed

### Requirement: Payment alert toast notification
The frontend SHALL display a toast notification when a payment alert event is received via the WebSocket event flow.

#### Scenario: Payment failed toast
- **WHEN** the frontend receives a `subscription_alert` event with `alert: "payment_failed"` via WebSocket/SSE
- **THEN** a vue-sonner warning toast SHALL be displayed with the payment failure message

#### Scenario: Payment succeeded toast
- **WHEN** the frontend receives a `subscription_alert` event with `alert: "payment_succeeded"` via WebSocket/SSE
- **THEN** a vue-sonner success toast SHALL be displayed indicating payment has been resolved
