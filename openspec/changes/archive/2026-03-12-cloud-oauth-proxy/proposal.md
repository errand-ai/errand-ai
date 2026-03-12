## Why

Most users deploying errand-server will not have (or know how to create) their own Google or Microsoft OAuth app credentials. Requiring each deployment to configure `GOOGLE_CLIENT_ID`/`SECRET` and `MICROSOFT_CLIENT_ID`/`SECRET` is a significant barrier to using the Google Drive and OneDrive integrations. Rather than distributing shared credentials with the errand deployment, we can leverage the existing errand-cloud service as an OAuth proxy — errand-cloud holds the OAuth app credentials and mediates the authentication flow, delivering tokens back to errand-server over the already-established authenticated WebSocket connection.

## What Changes

- The `/api/integrations/status` endpoint gains a `mode` field per provider: `"direct"` (local client credentials configured), `"cloud"` (no local credentials but cloud service connected), or `null` (neither available)
- The `/api/integrations/{provider}/authorize` endpoint checks for local credentials first; if absent and cloud is connected, it initiates the OAuth flow via errand-cloud by sending an `oauth_initiate` WebSocket message and redirecting the user to errand-cloud's OAuth authorize URL
- A new WebSocket message handler receives `oauth_tokens` messages from errand-cloud and stores the credentials in the database (same encrypted `PlatformCredential` storage as today)
- Token refresh for cloud-proxied credentials sends an `oauth_refresh` WebSocket message to errand-cloud instead of directly calling the provider's token endpoint
- The frontend integrations page shows contextual messaging based on the availability mode: direct connect, cloud-proxied connect, or a message explaining that either local credentials or a cloud subscription is required
- Users who configure their own `GOOGLE_CLIENT_ID`/`SECRET` or `MICROSOFT_CLIENT_ID`/`SECRET` continue to use the existing direct OAuth flow unchanged

## Capabilities

### New Capabilities
- `cloud-oauth-proxy`: WebSocket-based OAuth proxy flow — initiating OAuth via errand-cloud, receiving tokens over WebSocket, and refreshing tokens through the cloud service

### Modified Capabilities
- `cloud-storage-oauth`: The authorize endpoint, status endpoint, and token refresh logic gain cloud-proxy awareness (check for local credentials first, fall back to cloud proxy)
- `cloud-storage-ui`: The integration cards gain a third state for cloud-proxy availability and contextual messaging when neither local credentials nor cloud service are configured

## Impact

- **Backend**: `integration_routes.py` (status endpoint, authorize endpoint), `cloud_storage.py` (token refresh), `cloud_client.py` (new WS message handlers for `oauth_tokens` and `oauth_refresh` response)
- **Frontend**: `CloudStorageIntegration.vue` (availability states, messaging), `useApi.ts` (status response type update)
- **Dependencies**: No new dependencies — uses existing WebSocket infrastructure and credential storage
- **Coordination**: Requires corresponding changes in errand-cloud to implement the OAuth proxy endpoints and WebSocket message handling (see errand-cloud `cloud-oauth-proxy` change)
