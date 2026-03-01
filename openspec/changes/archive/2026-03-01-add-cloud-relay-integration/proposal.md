## Why

Users running errand locally cannot receive inbound webhooks from external services like Slack without configuring firewall port-forwarding rules. The errand-cloud service (https://service.errand.cloud) already provides publicly-addressable webhook endpoints, signature verification, message queuing, and WebSocket relay — but errand-server has no client to connect to it.

## What Changes

- errand-server gains a WebSocket client that connects to errand-cloud, receives relayed webhook payloads, and dispatches them to the appropriate Slack handlers
- OAuth Authorization Code flow with the errand-cloud Keycloak realm allows users to sign up / authenticate from the Settings page, with offline token storage and background refresh
- Slack webhook handler logic is refactored to separate signature verification from business logic, allowing cloud-relayed payloads to be dispatched directly (cloud already verified the signature)
- When the user has both Slack credentials configured and a cloud account connected, errand-server automatically registers webhook endpoints with the cloud service via its REST API
- A new "Cloud Service" settings subpage lets the user connect/disconnect, view connection status, and see cloud webhook endpoint URLs (conditional on Slack being enabled)
- A "Cloud Connected" indicator in the app header provides quick visual feedback on connection status

## Capabilities

### New Capabilities

- `cloud-auth`: OAuth Authorization Code flow with errand-cloud Keycloak (public client with PKCE), offline token storage in encrypted PlatformCredential, and background token refresh
- `cloud-websocket-client`: Persistent WebSocket client connecting to errand-cloud relay, implementing the errand-client-protocol (heartbeat, ACK, deduplication, reconnection with exponential backoff)
- `cloud-webhook-dispatch`: Routing of cloud-relayed webhook payloads to Slack handlers by integration and endpoint_type, bypassing local signature verification
- `cloud-endpoint-management`: Automatic registration of webhook endpoints with errand-cloud when Slack credentials and cloud account are both active
- `cloud-settings-ui`: Settings subpage for cloud service connection management, endpoint URL display, and connection status
- `cloud-status-indicator`: Header indicator showing cloud connection state (connected/disconnected/not configured)

### Modified Capabilities

- `slack-mention-events`: Extract event processing logic from route handler into standalone function callable from both HTTP route and cloud dispatcher
- `slack-commands`: Extract command processing logic from route handler into standalone function callable from both HTTP route and cloud dispatcher
- `slack-interactive-messages`: Extract interaction processing logic from route handler into standalone function callable from both HTTP route and cloud dispatcher
- `settings-navigation`: Add "Cloud Service" link to settings sidebar
- `admin-settings-api`: Add cloud status endpoint for frontend to poll connection state

## Impact

- **Backend**: New modules for cloud auth, WebSocket client, and webhook dispatch; refactored Slack route handlers; new API routes for cloud management; new background task for WebSocket client and token refresh; cloud credentials stored as PlatformCredential with platform_id "cloud"
- **Frontend**: New CloudServicePage.vue settings subpage; cloud status indicator in App.vue header; new API composable functions for cloud endpoints; new route `/settings/cloud`
- **No database migration**: Cloud credentials use existing PlatformCredential model; cloud endpoint URLs stored in Setting model
- **Dependencies**: `websockets` Python package for the WebSocket client (the existing `websockets` or `aiohttp` client)
