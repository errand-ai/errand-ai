## Context

errand is a locally-hosted task automation service with a FastAPI backend, Vue 3 frontend, and integrations with external services like Slack. Users behind NAT/firewalls cannot receive inbound webhooks from Slack without port forwarding.

errand-cloud (https://service.errand.cloud) is a companion relay service that receives webhooks on public endpoints, verifies their signatures, queues them in Valkey Streams, and relays them over WebSocket to connected errand instances. The cloud service already has a complete implementation: webhook ingestion, endpoint management API, WebSocket relay with heartbeat/ACK protocol, and Keycloak OIDC authentication.

This change adds the errand-side client: authentication with the cloud service, a WebSocket client for receiving relayed webhooks, direct dispatch to Slack handlers, automatic endpoint registration, and UI for managing the connection.

The errand-cloud Keycloak realm has social login (Google, GitHub) configured for user registration.

## Goals / Non-Goals

**Goals:**

- Users can sign up for / authenticate with errand-cloud from the errand Settings page
- errand-server maintains a persistent WebSocket connection to errand-cloud for receiving relayed webhooks
- Relayed Slack webhooks are dispatched directly to handler business logic (bypassing local signature verification since the cloud already verified)
- Webhook endpoints are automatically registered with errand-cloud when both Slack credentials and cloud account are active
- Cloud connection status is visible in the app header
- The connection survives token expiry via automatic offline token refresh

**Non-Goals:**

- Cloud-hosted frontend UI (future change)
- Multi-tenant cloud access to the local errand instance (future change)
- Relaying non-Slack integrations (GitHub, email — future, but architecture supports it)
- Bidirectional communication over the WebSocket (cloud-to-errand only for now)
- Cloud-side changes (handled in a separate errand-cloud change)

## Decisions

### D1: OAuth Authorization Code flow with PKCE (public client)

**Choice**: errand-server acts as a public OAuth client against the errand-cloud Keycloak realm. The auth flow uses Authorization Code with PKCE (no client secret). The user is redirected to Keycloak for login/registration, and the callback returns tokens to errand-server.

**Rationale**: errand is distributed as open-source, self-hosted software. A confidential client would require shipping or configuring a client secret, which is impractical. PKCE provides equivalent security for public clients. The `offline_access` scope is requested to obtain a refresh token that persists across access token expiry.

**Alternatives considered**:
- Confidential client — rejected because distributing client secrets with open-source software is insecure
- API key / manual token entry — rejected because it requires the user to use a separate cloud UI that doesn't exist yet
- Token exchange from existing errand OIDC — rejected because the errand and cloud Keycloak realms may be completely different identity providers

### D2: Store cloud credentials as PlatformCredential with platform_id "cloud"

**Choice**: Reuse the existing `PlatformCredential` model with `platform_id = "cloud"`. The encrypted_data JSON stores `access_token`, `refresh_token`, `token_expiry`, and `tenant_id` (the Keycloak `sub` claim). The `status` field tracks connection state.

**Rationale**: The PlatformCredential model already provides encrypted storage, status tracking, and last_verified_at — exactly what's needed. No database migration required. The credential loading pattern (`load_credentials("cloud", session)`) is consistent with other platform integrations.

**Alternatives considered**:
- New database model — rejected; PlatformCredential already has the right shape
- Settings table — rejected; settings aren't designed for structured encrypted data with status tracking

### D3: Store cloud endpoint URLs in Settings

**Choice**: When endpoints are registered with errand-cloud, the returned URLs are stored in the Settings table under key `cloud_endpoints` as a JSON list of `{integration, endpoint_type, url, token}` objects.

**Rationale**: Endpoint URLs are configuration data, not secrets. They need to be readable by the frontend for display. The Settings model is the right fit — it's JSONB storage accessible via the existing settings API.

### D4: Direct dispatch bypassing signature verification

**Choice**: Cloud-relayed webhook payloads are dispatched directly to Slack handler business logic without re-verifying the Slack signature. The WebSocket message includes `integration` and `endpoint_type` fields that determine routing.

**Rationale**: errand-cloud already verified the Slack signing secret. Re-verifying locally would fail because the signing secret used by the cloud service may differ from any locally-configured Slack credentials (and may not exist locally at all). The trust boundary is the authenticated WebSocket connection — if the cloud service sent it, it's verified.

**Implementation**: Refactor each Slack route handler to separate verification from processing:
- `slack_events` → extract `process_slack_event(body: bytes)`
- `slack_commands` → extract `process_slack_command(body: bytes, session)`
- `slack_interactions` → extract `process_slack_interaction(body: bytes, session)`

The HTTP routes call verify → process. The cloud dispatcher calls process directly.

### D5: WebSocket client as a background task in the main server process

**Choice**: The WebSocket client runs as an `asyncio.create_task()` in the FastAPI lifespan, alongside existing background tasks (scheduler, zombie cleanup, slack status updater, etc.).

**Rationale**: Consistent with the existing background task pattern. The WebSocket client is I/O-bound and cooperative — it won't block the event loop. Running in-process means it has direct access to the database session factory and can call handler functions directly.

**Lifecycle**:
1. On startup: if cloud credentials exist with status "connected", start the WebSocket client task
2. On connect from settings: start the task dynamically
3. On disconnect from settings: cancel the task
4. On shutdown: cancel the task (consistent with other background tasks)

### D6: Background token refresh task

**Choice**: A separate background task monitors the access token expiry and refreshes it using the offline refresh token before it expires. The task runs alongside the WebSocket client and refreshes when the token is within 60 seconds of expiry.

**Rationale**: The errand-client-protocol spec requires proactive token refresh. The existing WebSocket connection continues to work (the server validated the token at connect time), but the refreshed token is needed for any reconnection and for REST API calls (endpoint management).

**Implementation**: The refresh task uses the Keycloak token endpoint directly (same as the existing SSO refresh flow in auth_routes.py). On refresh failure, the WebSocket connection continues until the server closes it, then the user is prompted to re-authenticate.

### D7: Cloud status broadcast via existing task events WebSocket

**Choice**: Cloud connection status changes are published via the existing Valkey `task_events` channel as `cloud_status` events. The frontend task WebSocket receives these and updates the header indicator.

**Rationale**: Reuses the existing real-time event infrastructure. No new WebSocket endpoints or polling needed. The frontend already listens to `task_events` for task updates — adding a `cloud_status` event type is trivial.

**Event format**:
```json
{"event": "cloud_status", "status": "connected"}
{"event": "cloud_status", "status": "disconnected"}
{"event": "cloud_status", "status": "error", "detail": "..."}
```

### D8: Cloud auth callback route

**Choice**: New routes at `/api/cloud/auth/login` (initiates OAuth flow) and `/api/cloud/auth/callback` (handles redirect from Keycloak). The callback exchanges the authorization code for tokens, stores them encrypted, starts the WebSocket client, and redirects the user back to the cloud settings page.

**Rationale**: The OAuth flow requires server-side callback handling. Separate from the existing `/auth/*` routes (which are for errand's own SSO) to avoid confusion. The `/api/cloud/` prefix groups all cloud-related endpoints.

### D9: Auto-register endpoints on dual activation

**Choice**: Endpoint registration with errand-cloud is triggered when both conditions are met: (1) cloud account is connected, and (2) Slack credentials are configured. This check runs in two places:
- After successful cloud authentication (check if Slack is already enabled)
- After Slack credentials are saved (check if cloud is already connected)

**Rationale**: The user may enable Slack before or after connecting to the cloud. Either ordering should work seamlessly. The signing secret is read from the locally-stored Slack credentials and sent to errand-cloud's `POST /api/endpoints` API.

### D10: Hardcoded cloud service URL with setting override

**Choice**: The errand-cloud service URL defaults to `https://service.errand.cloud` but can be overridden via a `cloud_service_url` setting. The Keycloak discovery URL is derived from the cloud service's well-known configuration, or provided as a separate setting.

**Rationale**: For production use, the URL is fixed. For development and self-hosted errand-cloud deployments, users need to point to a different URL. Keycloak configuration (realm URL, client ID) will be provided by errand-cloud via a discovery endpoint or hardcoded for the shared Keycloak instance.

## Risks / Trade-offs

**WebSocket client resilience** — Network interruptions, cloud service restarts, or Keycloak outages will disconnect the WebSocket. Mitigated by exponential backoff reconnection (matching the errand-client-protocol spec) and clear UI indication of connection state.

**Token management complexity** — Offline tokens can be revoked by Keycloak admins, expire after long inactivity periods, or become invalid after realm configuration changes. Mitigated by clear error states in the UI and prompting the user to re-authenticate.

**Slack handler refactoring risk** — Separating verification from processing in three route handlers could introduce bugs if the function boundaries are drawn incorrectly. Mitigated by ensuring existing tests continue to pass and adding new tests for the extracted functions.

**Dual-trigger endpoint registration** — Registering endpoints from two code paths (cloud connect + Slack enable) could cause race conditions or duplicate registrations. Mitigated by checking for existing cloud endpoints before creating new ones (idempotent registration).

**Cloud service dependency for Slack webhooks** — When using the cloud relay, Slack webhooks depend on the cloud service being available. If the cloud service is down, webhooks are queued (48h retention) but not delivered. The user can still configure direct Slack webhooks as a fallback.
