## Why

When the Keycloak access token expires during a session, any API call triggers a hard redirect to `/auth/login`, which causes a full-page reload and loses all in-progress UI state — including task prompts the user is typing. The current flow has no mechanism to silently refresh tokens, so even short-lived token expiry (typically 5 minutes) disrupts the user experience unnecessarily.

## What Changes

- Backend login endpoint adds `offline_access` to the OIDC scope, so Keycloak issues a refresh token alongside the access token
- Backend gains a new `POST /auth/refresh` endpoint that accepts a refresh token and returns a fresh access token (and optionally a rotated refresh token)
- Backend callback passes the refresh token to the frontend alongside the access and ID tokens
- Frontend auth store manages the refresh token and tracks token expiry
- Frontend proactively refreshes the access token before it expires using a background timer
- Frontend API layer retries a failed 401 request once after attempting a token refresh, only redirecting to login if the refresh itself fails
- The hard redirect to `/auth/login` on 401 becomes a last resort, not the default behaviour

## Capabilities

### New Capabilities

_(none — this change modifies existing auth capabilities)_

### Modified Capabilities

- `keycloak-auth`: Login adds `offline_access` scope; callback returns refresh token; new `POST /auth/refresh` endpoint exchanges a refresh token for fresh tokens
- `frontend-auth`: Auth store manages refresh token and expiry; background timer proactively refreshes before expiry; API layer retries 401s with a refreshed token before redirecting to login

## Impact

- **Backend**: `auth_routes.py` — modified login (scope), callback (refresh token passthrough), new refresh endpoint
- **Backend**: `auth.py` — no changes expected (token validation unchanged)
- **Frontend**: `stores/auth.ts` — new refresh token state, expiry tracking, refresh timer
- **Frontend**: `composables/useApi.ts` — 401 handler retries after refresh attempt
- **Frontend**: `App.vue` — token init handles refresh token from URL fragment
- **Keycloak config**: The Keycloak client must have offline access enabled (client scope `offline_access` must be assigned) — this is an external configuration prerequisite, not a code change
- **Security**: Refresh tokens are long-lived and sensitive; they are stored only in browser memory (not localStorage) and are never sent to the resource API, only to the `/auth/refresh` endpoint
