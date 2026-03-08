## Approach

### Message Flow

errand-cloud publishes `subscription_alert` messages to the Valkey pubsub channel `tenant:{id}:notify`. The errand-server WebSocket client already listens on this channel in its pubsub loop. Currently it only triggers webhook drain on messages — we extend it to handle structured JSON alert messages.

```
errand-cloud                errand-server              errand-desktop
     │                           │                          │
     │ Valkey pubsub             │                          │
     │ tenant:{id}:notify        │                          │
     │ {"type":                  │                          │
     │  "subscription_alert",    │                          │
     │  "alert":"payment_failed",│                          │
     │  ...}                     │                          │
     │──────────────────────────▶│                          │
     │                           │                          │
     │                           │ 1. Store payment status  │
     │                           │    in Settings table     │
     │                           │                          │
     │                           │ 2. Emit WebSocket event  │
     │                           │    to errand-desktop      │
     │                           │────────────────────────▶ │
     │                           │                          │
     │                           │ 3. Update cloud status   │
     │                           │    API response           │
     │                           │                          │
     │                           │ GET /api/cloud/status     │
     │                           │ { subscription: {         │
     │                           │     active: true,         │
     │                           │     expires_at: "...",     │
     │                           │     payment_warning: {     │
     │                           │       alert: "...",        │
     │                           │       next_retry_at: "..." │
     │                           │     }                      │
     │                           │   }                        │
     │                           │ }                          │
```

### Pubsub Message Handling

Extend the WebSocket client's pubsub loop to parse incoming messages as JSON. If the message has `"type": "subscription_alert"`, handle it as a payment notification rather than triggering webhook drain.

Message format from errand-cloud:

```json
{
  "type": "subscription_alert",
  "alert": "payment_failed",
  "plan": "monthly",
  "attempt_count": 1,
  "next_retry_at": "2026-03-12T14:00:00Z",
  "final_attempt": false
}
```

Alert types: `payment_failed`, `payment_succeeded`.

### Payment Status Storage

Store received payment alerts in the Settings table (existing key-value store pattern) under key `cloud_payment_warning`. Clear it on `payment_succeeded`.

### Cloud Status API Update

Extend `GET /api/cloud/status` response to include `payment_warning` in the `subscription` object when a `cloud_payment_warning` Setting exists. The cloud-settings-ui spec already handles subscription expiry display — payment warnings appear alongside it.

### Cloud Settings UI Update

On the Cloud Service settings page (`/settings/cloud`), when `payment_warning` is present in the status response:
- Show a warning indicator (amber/orange) next to the subscription expiry
- Display message: "Payment failed — retrying {date}" or "Payment failed — subscription expired"
- This sits alongside the existing "Subscription expires {date}" line

### Desktop Forwarding

Forward the `subscription_alert` payload to errand-desktop via the existing WebSocket event mechanism (structured task events / SSE pattern). errand-desktop will handle native macOS notifications independently.

### Toast Notification

Show a vue-sonner toast in the errand-server web UI when a payment alert is received via the pubsub → WebSocket event flow, using the existing toast notification system.
