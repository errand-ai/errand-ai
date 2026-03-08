## Why

errand-cloud is integrating Stripe for paid subscriptions. When a renewal payment fails, errand-cloud publishes a `subscription_alert` message via Valkey pubsub. The errand-server (local relay) needs to receive these alerts and surface them to the user — both in the Cloud Service settings page and by forwarding to errand-desktop for native OS notifications.

## What Changes

- Handle new `subscription_alert` message type from Valkey pubsub (`tenant:{id}:notify` channel)
- Display payment status alongside "Subscription expires" on the Cloud Service settings page
- Forward payment alert events to errand-desktop via the existing IPC/communication channel
- Alert types: `payment_failed` (with retry info), `payment_succeeded` (resolution), `subscription_expired` (final failure)

## Capabilities

### New Capabilities

- `payment-status-display`: Show payment failure warnings in Cloud Service settings (e.g., "Payment failed — retrying 12 Mar", "Payment failed — subscription expired")

### Modified Capabilities

- `cloud-service-settings`: Add payment status indicator next to subscription expiry message
- `errand-client-protocol`: Handle `subscription_alert` pubsub message type, forward to desktop app

## Impact

- **Cloud Service settings page**: New warning indicator when payment issues exist
- **Pubsub handler**: Extend `_pubsub_loop()` equivalent to handle `subscription_alert` messages alongside existing webhook notifications
- **Desktop forwarding**: Pass alert payload to errand-desktop via existing communication mechanism
- **No new dependencies expected**
