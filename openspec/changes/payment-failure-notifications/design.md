## Approach

### Message Flow

When a Stripe renewal fails, errand-cloud relays a `subscription_alert` message to the connected errand-server over the existing WebSocket tunnel (the same connection that carries `webhook`, `proxy_request`, and `oauth_tokens` messages). The errand-server WebSocket client already dispatches inbound messages by their `type` field in `CloudWebSocketClient._handle_message`; we add a `subscription_alert` branch alongside the existing ones. Messages of other types (or non-JSON frames, which are rejected before dispatch) are unaffected and continue to their existing handlers.

```
errand-cloud                errand-server              errand-desktop
     │                           │                          │
     │ WebSocket tunnel          │                          │
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

### Message Handling

Add a `subscription_alert` branch to `CloudWebSocketClient._handle_message`. Inbound tunnel frames are already parsed as JSON and dispatched by their `type` field; when `"type": "subscription_alert"`, handle it as a payment notification. Other message types (`webhook`, `proxy_request`, …) continue to their existing branches.

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

Forward the `subscription_alert` payload to errand-desktop by sending a `push_event` on the `system` channel over the WebSocket tunnel — the same push_event mechanism used to forward subscribed Valkey channels — but only when the desktop has subscribed to `system`. errand-desktop handles native macOS notifications independently.

### Toast Notification

The handler also re-publishes the alert on the local event bus (`publish_event("subscription_alert", …)`), which reaches the errand-server web UI over the existing SSE stream (`/api/events`). The frontend raises a vue-sonner toast using the existing toast notification system.
