## Tasks

### Backend: Status endpoint cloud-proxy awareness

- [x] Add `_cloud_available()` helper to `integration_routes.py` that checks if cloud `PlatformCredential` exists with `status: "connected"`
- [x] Update `_provider_available()` to return a tuple `(available: bool, mode: str | None)` — checks local credentials first (`"direct"`), then cloud (`"cloud"`), else `(False, None)`
- [x] Update `/api/integrations/status` endpoint to include `mode` field in each provider's response
- [x] Add tests for status endpoint with direct mode, cloud mode, and unavailable states

### Backend: Cloud-proxy authorize flow

- [x] Update `/api/integrations/{provider}/authorize` to detect missing local credentials and fall back to cloud-proxy flow
- [x] In cloud-proxy path: generate state token, send `oauth_initiate` WS message via cloud client, store state in Valkey, redirect to `{cloud_service_url}/oauth/{provider}/authorize?state={state}`
- [x] Update error message when neither local credentials nor cloud are available
- [x] Add tests for authorize endpoint cloud-proxy fallback

### Backend: WebSocket token reception

- [x] Add `oauth_tokens` message handler in `cloud_client.py` `_handle_message()` — decrypt/store credentials in `PlatformCredential`, publish `cloud_storage_connected` SSE event
- [x] Add `oauth_error` message handler — log error, publish `cloud_storage_error` SSE event
- [x] Add tests for WebSocket message handlers (token storage, error handling)

### Backend: Cloud-proxy token refresh

- [x] Update `refresh_token_if_needed()` in `cloud_storage.py` to check for local client credentials first
- [x] When no local credentials: send `oauth_refresh` over WebSocket, await `oauth_refresh_result` with timeout
- [x] Handle `oauth_error` response (log warning, return None to skip injection)
- [x] Handle disconnected WebSocket case (log warning, return None)
- [x] Add helper to cloud_client.py for sending a message and awaiting a typed response with timeout
- [x] Add tests for cloud-proxy refresh path (success, error, disconnected)

### Frontend: Integration card three-state UI

- [x] Update `CloudStorageProviderStatus` type in `useApi.ts` to include `mode: 'direct' | 'cloud' | null`
- [x] Update `CloudStorageIntegration.vue` unavailable message to distinguish between "not configured" (no MCP URL) and "no credentials or cloud" (MCP URL exists but no auth path)
- [x] Add SSE event listener for `cloud_storage_connected` to auto-refresh integration status
- [x] Add tests for the three availability states in the integration card
