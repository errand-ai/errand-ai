## 1. Refactor Slack route handlers to separate verification from processing

- [x] 1.1 In `errand/platforms/slack/routes.py`, extract the event processing logic from `slack_events` into a standalone `process_slack_event(body: bytes)` async function — handles `event_callback` with `app_mention`, duplicate detection, and background task creation. The HTTP route becomes: verify → call process function → return response
- [x] 1.2 Extract the command processing logic from `slack_commands` into `process_slack_command(body: bytes, session: AsyncSession, response_url_callback=None)` — parses form data, dispatches subcommands, handles channel message posting. Add a `response_url_callback` parameter: when provided (cloud relay path), POST the response to this URL instead of returning it as JSON
- [x] 1.3 Extract the interaction processing logic from `slack_interactions` into `process_slack_interaction(body: bytes, session: AsyncSession)` — parses payload, dispatches block_actions, posts to response_url. This function already uses response_url for delivery, so minimal changes needed
- [x] 1.4 Verify all existing Slack route tests still pass with the refactored code

## 2. Cloud auth module and API routes

- [x] 2.1 Create `errand/cloud_auth.py` with: PKCE code_verifier/code_challenge generation, Keycloak discovery URL derivation from cloud service URL, OAuth state management (in-memory dict with TTL), token exchange function, and token refresh function
- [x] 2.2 Add cloud configuration settings to `errand/settings_registry.py`: `cloud_service_url` (default: `https://service.errand.cloud`, not sensitive), `cloud_keycloak_realm_url` (default derived from cloud service, not sensitive), `cloud_keycloak_client_id` (default: `errand-desktop`, not sensitive), `cloud_endpoints` (default: `[]`, not sensitive)
- [x] 2.3 Add `GET /api/cloud/auth/login` route in `errand/main.py` — generates PKCE challenge, stores state, redirects to Keycloak authorization endpoint with `scope=openid offline_access`
- [x] 2.4 Add `GET /api/cloud/auth/callback` route — exchanges code for tokens with PKCE verifier, extracts tenant_id from `sub` claim, stores encrypted credentials as PlatformCredential `platform_id="cloud"`, redirects to `/settings/cloud`
- [x] 2.5 Add `POST /api/cloud/auth/disconnect` route — stops WebSocket client, revokes cloud endpoints, deletes cloud credentials and settings, publishes `cloud_status` disconnected event
- [x] 2.6 Add `GET /api/cloud/status` route — returns current cloud connection state (`not_configured`, `connected`, `error`) with tenant_id and cloud endpoints if connected

## 3. Cloud WebSocket client

- [x] 3.1 Create `errand/cloud_client.py` with an async `CloudWebSocketClient` class: connects to `wss://{cloud_service_url}/ws` with Bearer token, implements receive loop for webhook/ping messages, sends ACK/pong responses, tracks processed message IDs for deduplication
- [x] 3.2 Implement exponential backoff reconnection in the client: 0-500ms jitter on first attempt, doubling to 30s cap, reset on successful connect. Do not reconnect on close codes 4001 (superseded) or 4003 (disabled). On 4002 (auth_expired), attempt token refresh before reconnecting
- [x] 3.3 Implement `cloud_status` event publishing: publish to `task_events` Valkey channel on connect, disconnect, and error state changes
- [x] 3.4 Integrate the WebSocket client into the FastAPI lifespan in `errand/main.py`: on startup, check for cloud credentials and start client task if connected; store task reference for cancellation on shutdown. Add a module-level function to start/stop the client dynamically (called from auth routes)
- [x] 3.5 Add `websockets` to `errand/requirements.txt` (or use `aiohttp` if already a dependency for the WebSocket client)

## 4. Cloud webhook dispatcher

- [x] 4.1 Create `errand/cloud_dispatch.py` with a `dispatch_cloud_webhook(message: dict)` async function: routes by `integration` and `endpoint_type` to the extracted Slack processing functions from step 1. Logs warnings for unknown integrations. Creates a database session for handler calls
- [x] 4.2 Wire the dispatcher into `CloudWebSocketClient.on_message()` — when a `type: "webhook"` message is received, call the dispatcher, then send ACK

## 5. Cloud endpoint auto-registration

- [x] 5.1 Create `errand/cloud_endpoints.py` with async functions: `register_cloud_endpoints(cloud_creds, slack_creds, session)` — calls `POST /api/endpoints` on errand-cloud with Slack signing secret, stores returned URLs in `cloud_endpoints` setting; `revoke_cloud_endpoints(cloud_creds)` — calls `DELETE /api/endpoints?integration=slack`; `check_existing_endpoints(cloud_creds)` — calls `GET /api/endpoints?integration=slack` to avoid duplicates
- [x] 5.2 Call `register_cloud_endpoints` from the cloud OAuth callback (step 2.4) after successful authentication, if Slack credentials are already configured
- [x] 5.3 Call `register_cloud_endpoints` from the Slack credential save handler (`PUT /api/platforms/slack/credentials` in main.py) after successful credential save, if cloud credentials are already connected
- [x] 5.4 Call `revoke_cloud_endpoints` from the cloud disconnect handler (step 2.5)

## 6. Background token refresh

- [x] 6.1 Add a `_token_refresh_loop()` method to `CloudWebSocketClient` or create a separate background task in `cloud_auth.py` — periodically checks token expiry, refreshes when within 60 seconds of expiry, updates encrypted PlatformCredential. On refresh failure, log warning and set status to "error" after WebSocket disconnects
- [x] 6.2 Start the token refresh task alongside the WebSocket client task in the lifespan; cancel on shutdown

## 7. Frontend: Cloud Service settings page

- [x] 7.1 Create `frontend/src/pages/settings/CloudServicePage.vue` — fetches cloud status from `GET /api/cloud/status` on mount; displays not-connected / connected / error states with appropriate actions (Connect / Disconnect / Reconnect buttons)
- [x] 7.2 Add "Connect to Errand Cloud" button that navigates to `/api/cloud/auth/login` (full page navigation, not SPA — OAuth redirect)
- [x] 7.3 Add "Disconnect" button that calls `POST /api/cloud/auth/disconnect` and refreshes state
- [x] 7.4 Add cloud endpoint URL display section — conditionally shown when cloud is connected AND `cloud_endpoints` is non-empty; lists each endpoint with integration, type, URL, and "Copy" button
- [x] 7.5 Add message when cloud is connected but Slack is not enabled: "Enable Slack in Integrations to configure cloud webhook endpoints"
- [x] 7.6 Handle OAuth callback redirect: when the page loads with an `error` query parameter, display the error as a toast

## 8. Frontend: Settings navigation and routing

- [x] 8.1 Add route `/settings/cloud` → `CloudServicePage.vue` in `frontend/src/router/index.ts` (under the settings children)
- [x] 8.2 Add "Cloud Service" link to the settings sidebar in `frontend/src/pages/SettingsPage.vue` — positioned after "Integrations", before "Task Profiles"

## 9. Frontend: Cloud status indicator in header

- [x] 9.1 Add cloud status state to the App.vue component — fetch initial status from `GET /api/cloud/status` on mount; update in real-time from `cloud_status` events on the existing task events WebSocket
- [x] 9.2 Add cloud indicator to the header — cloud icon + "Connected"/"Disconnected" text, green/amber coloring, positioned before the version indicator. Hidden when status is `not_configured`

## 10. Backend tests

- [x] 10.1 Test cloud auth login route: generates PKCE challenge, redirects to correct Keycloak URL, returns 503 when not configured
- [x] 10.2 Test cloud auth callback: exchanges code for tokens, stores encrypted credentials, redirects to settings page; handles error responses
- [x] 10.3 Test cloud disconnect: deletes credentials, publishes status event; idempotent when not connected
- [x] 10.4 Test cloud status endpoint: returns correct state for not_configured, connected, and error scenarios
- [x] 10.5 Test cloud WebSocket client: connects with Bearer token, handles webhook messages with ACK, responds to pings with pong, deduplicates messages
- [x] 10.6 Test cloud WebSocket reconnection: exponential backoff on network error, no reconnect on 4001/4003, refresh attempt on 4002
- [x] 10.7 Test cloud webhook dispatch: routes Slack events/commands/interactivity to correct handlers, logs warning for unknown integration
- [x] 10.8 Test cloud endpoint registration: calls cloud API with correct payload, stores URLs, skips if endpoints already exist
- [x] 10.9 Test token refresh: refreshes before expiry, updates stored credentials, handles refresh failure
- [x] 10.10 Test refactored Slack handlers: existing behavior preserved when called via HTTP route, correct behavior when called from cloud dispatcher (no verification, response_url delivery for commands)

## 11. Frontend tests

- [x] 11.1 Test CloudServicePage: renders not-connected state with Connect button, renders connected state with Disconnect button and endpoints, renders error state with Reconnect button
- [x] 11.2 Test cloud endpoint display: shows endpoints when Slack is enabled, hides when Slack is not enabled, copy button works
- [x] 11.3 Test header cloud indicator: shown when connected (green), shown when disconnected (amber), hidden when not configured, updates on cloud_status WebSocket events
- [x] 11.4 Test settings navigation: Cloud Service link appears in sidebar, navigates to correct route
