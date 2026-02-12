## Context

The app uses Keycloak OIDC Authorization Code flow. The backend is a confidential client that exchanges the auth code for tokens, then passes the access token and ID token to the frontend via URL fragment. The frontend stores these in a Pinia store (memory only) and attaches the access token as a Bearer header on API calls.

Currently, when the access token expires (Keycloak default: 5 minutes), the next API call returns 401. The frontend's `authFetch` wrapper in `useApi.ts` immediately clears the token and does `window.location.href = '/auth/login'` — a full-page redirect that destroys all UI state, including any text the user was typing.

There is no refresh token flow. The login scope is `openid` only (no `offline_access`), so Keycloak doesn't issue a refresh token. Even if it did, nothing in the frontend or backend handles refresh.

## Goals / Non-Goals

**Goals:**
- Seamless token renewal: users should never be interrupted by token expiry during normal usage
- Proactive refresh: renew the access token before it expires, not after a 401
- Graceful fallback: if refresh fails (e.g. refresh token revoked, Keycloak down), fall back to login redirect — but only as a last resort
- No state loss: the user's in-progress work (typed text, open modals, scroll position) must survive a token refresh

**Non-Goals:**
- Persisting tokens across page reloads (tokens remain in memory only — a full page reload requires re-authentication, which is acceptable)
- Sliding session / extending refresh token lifetime beyond Keycloak's configured expiry
- Refresh token rotation handling beyond what Keycloak returns (if Keycloak returns a new refresh token, we use it; we don't implement our own rotation logic)
- Offline support or service worker token caching

## Decisions

### 1. Backend-mediated refresh (not frontend-direct)

The refresh token exchange requires `client_secret`, which must not be exposed to the frontend. The backend will provide a `POST /auth/refresh` endpoint that accepts a refresh token in the request body, performs the token exchange with Keycloak, and returns the new tokens.

**Alternative considered**: Frontend calls Keycloak token endpoint directly. Rejected because the client is confidential (has a secret), and exposing the secret to the frontend would be a security violation.

### 2. Refresh token delivered via URL fragment alongside access token

The callback redirect already uses the URL fragment to pass `access_token` and `id_token`. The refresh token will be added as `refresh_token=<value>` in the same fragment. This keeps the delivery mechanism consistent.

**Alternative considered**: Backend stores refresh token server-side in a session/cookie. Rejected because the backend is stateless (no session store), and adding server-side session state would be a larger architectural change. HttpOnly cookies were considered but would require CSRF protection and change the API auth model from Bearer tokens.

### 3. Proactive refresh using a timer based on token `exp` claim

The frontend will decode the access token's `exp` claim and set a `setTimeout` to refresh the token a configurable margin before expiry (e.g. 30 seconds before). This avoids the race condition of discovering expiry only on a 401.

**Alternative considered**: Refresh only on 401 (reactive). Rejected because it still causes one failed request and requires retry logic. Proactive refresh is simpler for the happy path and reactive retry is kept as a safety net.

### 4. 401 retry with refresh — one attempt only

If a 401 occurs despite the proactive timer (e.g. clock skew, timer drift), the `authFetch` wrapper will attempt one token refresh and retry the original request. If the retry also fails, or if the refresh itself fails, fall back to login redirect as today.

**Alternative considered**: Queuing multiple concurrent requests during refresh. This adds complexity (promise deduplication, queue management). Given our low request concurrency, a simple single-retry is sufficient. If multiple requests 401 simultaneously, they'll each attempt refresh independently — the endpoint is idempotent so this is safe, just slightly redundant.

### 5. Refresh token stored in Pinia store (memory only)

Like the access token, the refresh token lives only in the Pinia store — never in localStorage or sessionStorage. This means a page reload loses the refresh token and requires a fresh login, which is acceptable (see Non-Goals).

**Alternative considered**: localStorage for persistence across reloads. Rejected because refresh tokens are long-lived credentials; storing them in localStorage exposes them to XSS. Memory-only storage limits exposure to the current page lifecycle.

## Risks / Trade-offs

- **[Keycloak offline_access scope not enabled]** → The Keycloak client must have the `offline_access` scope assigned. If it's missing, Keycloak won't issue refresh tokens and the flow silently degrades to the current behaviour (no refresh token in response). Mitigation: document the prerequisite; the frontend should handle the absence of a refresh token gracefully (skip refresh timer, fall back to current 401→redirect).
- **[Refresh token in URL fragment]** → URL fragments are visible in browser history and could leak via referrer headers. Mitigation: the fragment is cleared immediately on extraction (existing behaviour for access_token). Refresh tokens are opaque to the browser — Keycloak validates them, not the frontend. The window of exposure is the same as for the access token today.
- **[Token refresh fails silently]** → If the refresh endpoint is unreachable or Keycloak revokes the refresh token, the user will eventually be redirected to login. Mitigation: this is the intended fallback. The user loses no more state than they do today; the improvement is that this happens far less frequently.
- **[Clock skew between frontend and Keycloak]** → If the frontend's clock is ahead of Keycloak's, the proactive refresh margin may not be sufficient. Mitigation: the 401 retry mechanism catches this case. A 30-second margin should handle typical clock drift.
