## Design

### Overview

errand-cloud becomes an OAuth credential proxy for Google Drive and OneDrive integrations. errand-server instances that lack locally-configured OAuth client credentials can delegate the OAuth flow to errand-cloud, which holds the OAuth app credentials centrally. Tokens are delivered securely over the existing authenticated WebSocket connection, and token refresh also routes through errand-cloud since refresh token grants require the client_id/secret.

### Architecture

```
Direct flow (local credentials configured):
  errand-server ──redirect──▶ Google/Microsoft ──callback──▶ errand-server
  (unchanged from today)

Cloud proxy flow (no local credentials, cloud connected):
  1. errand-server sends oauth_initiate over WS to errand-cloud
  2. errand-server redirects user to errand-cloud/oauth/{provider}/authorize?state=...
  3. errand-cloud redirects to Google/Microsoft consent screen
  4. Google/Microsoft callbacks to errand-cloud (fixed redirect_uri)
  5. errand-cloud exchanges code for tokens (using its client_id/secret)
  6. errand-cloud looks up state → WS connection, delivers tokens over WS
  7. errand-server stores tokens in PlatformCredential (same as direct flow)
```

### Availability Resolution

The status endpoint resolves provider availability in priority order:

1. **Direct mode**: `{provider}_CLIENT_ID` + `{provider}_CLIENT_SECRET` + MCP URL all configured → `mode: "direct"`, `available: true`
2. **Cloud mode**: No local credentials, but cloud PlatformCredential exists with `status: "connected"` and MCP URL is configured → `mode: "cloud"`, `available: true`
3. **Unavailable**: Neither condition met → `mode: null`, `available: false`

### OAuth State Correlation (Option B)

errand-server generates a random state token and sends it to errand-cloud via WebSocket before redirecting the user. errand-cloud stores the state in a server-side map (`state → {tenant_id, provider}`, TTL 10 minutes). When the OAuth callback arrives, errand-cloud looks up the state to find the tenant's WebSocket connection and delivers tokens.

This avoids encoding user identity in the state (which would need signing) and keeps the mapping server-side on errand-cloud.

### WebSocket Message Protocol

Three new message types on the existing errand-client-protocol:

**`oauth_initiate`** (errand-server → errand-cloud):
```json
{
  "type": "oauth_initiate",
  "state": "random_token_urlsafe_32",
  "provider": "google_drive"
}
```

**`oauth_tokens`** (errand-cloud → errand-server):
```json
{
  "type": "oauth_tokens",
  "state": "random_token_urlsafe_32",
  "provider": "google_drive",
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 3600,
  "user_email": "user@gmail.com",
  "user_name": "User Name"
}
```

**`oauth_refresh`** (errand-server → errand-cloud):
```json
{
  "type": "oauth_refresh",
  "provider": "google_drive",
  "refresh_token": "..."
}
```

**`oauth_refresh_result`** (errand-cloud → errand-server):
```json
{
  "type": "oauth_refresh_result",
  "provider": "google_drive",
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 3600
}
```

**`oauth_error`** (errand-cloud → errand-server, for both initiate and refresh failures):
```json
{
  "type": "oauth_error",
  "state": "...",
  "provider": "google_drive",
  "error": "token_exchange_failed"
}
```

### Token Refresh Strategy

When `cloud_storage.refresh_token_if_needed()` detects an expired token:
- If local client credentials exist → refresh directly with provider (existing behavior)
- If no local credentials → send `oauth_refresh` over WebSocket to errand-cloud, await `oauth_refresh_result`

The refresh is synchronous from the caller's perspective (the worker awaits the result before proceeding with task execution).

### Frontend UX

The integration cards have three visual states based on the `mode` field:

- **`mode: "direct"`**: "Connect" button, same behavior as today
- **`mode: "cloud"`**: "Connect" button, triggers the cloud proxy authorize flow (same `/api/integrations/{provider}/authorize` endpoint — the backend decides the flow)
- **`mode: null`**: Card greyed out with message: "Configure Google/Microsoft credentials or connect to errand cloud to enable this integration"

After the cloud proxy flow completes, the frontend detects the connection via an SSE event (`cloud_storage_connected`) published when tokens arrive over WebSocket. The integration card updates without requiring a page refresh.

### Security Considerations

- Tokens are encrypted at rest in errand-server's database (existing Fernet encryption)
- Token delivery over WebSocket is protected by the existing authenticated WS connection (bearer token auth)
- OAuth state tokens have a 10-minute TTL on errand-cloud to prevent stale flows
- errand-cloud never stores the tokens — it's a pass-through proxy
- The existing direct flow remains available for users who prefer to manage their own OAuth apps
- If the WebSocket disconnects during the OAuth flow, errand-cloud drops the pending state — the user simply retries

### Files Changed

| File | Changes |
|------|---------|
| `errand/integration_routes.py` | Add `mode` to status response, cloud-proxy authorize flow |
| `errand/cloud_client.py` | Handle `oauth_tokens`, `oauth_refresh_result`, `oauth_error` messages |
| `errand/cloud_storage.py` | Cloud-proxy token refresh path |
| `frontend/src/components/settings/CloudStorageIntegration.vue` | Three-state availability UI |
| `frontend/src/composables/useApi.ts` | Update `CloudStorageProviderStatus` type with `mode` field |
