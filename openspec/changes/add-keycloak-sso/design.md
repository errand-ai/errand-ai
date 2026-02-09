## Context

The content-manager app is an open, unauthenticated Kanban task processor. All API endpoints and the frontend are publicly accessible. Before deploying to Kubernetes behind a real FQDN, we need to add user authentication via the organization's existing Keycloak instance at `id.devops-consultants.net`.

Current state:
- Backend: FastAPI with 5 endpoints under `/api/*`, all unauthenticated
- Frontend: Vue 3 SPA served by nginx, proxies `/api/*` to backend
- Helm: Single ingress routing all traffic to frontend service
- No user model, no session management, no auth middleware

## Goals / Non-Goals

**Goals:**
- Authenticate users via Keycloak OIDC before they can access the app
- Protect all `/api/*` endpoints with JWT Bearer token validation
- Keep KEDA metrics accessible internally without authentication
- Support single-FQDN deployment with path-based ingress routing
- Work in both local Docker Compose and Kubernetes environments

**Non-Goals:**
- User management UI (Keycloak handles this)
- Granular role-based access control (future change — for now, any role grants full access)
- Refresh token rotation or silent token renewal (out of scope for MVP)
- Running a local Keycloak instance in Docker Compose (use the shared instance)
- User data storage in the app database (no users table)

## Decisions

### 1. Authorization Code flow (confidential client), backend handles callback

The backend acts as an OIDC Relying Party. The flow:
1. Frontend detects unauthenticated state → redirects browser to `/auth/login`
2. `/auth/login` redirects to Keycloak's authorization endpoint with `client_id`, `redirect_uri=/auth/callback`, and `response_type=code`
3. User authenticates at Keycloak → Keycloak redirects to `/auth/callback?code=...`
4. Backend exchanges the code for tokens using `client_id` + `client_secret` (server-side, secret never exposed)
5. Backend returns the access token to the frontend (via redirect with token in a fragment or a short-lived cookie)
6. Frontend stores the access token and includes it as `Authorization: Bearer <token>` on all `/api/*` requests

**Why not PKCE/SPA flow:** We have a `CLIENT_SECRET` (confidential client), so server-side code exchange is more secure — the secret never reaches the browser.

**Why not session cookies:** Bearer tokens keep the backend stateless (no server-side session store). Multiple backend replicas work without sticky sessions or shared session storage.

### 2. JWT validation via JWKS

The backend validates access tokens by fetching Keycloak's public keys from the JWKS endpoint (`/protocol/openid-connect/certs`). Keys are cached in memory with a TTL to avoid per-request fetches.

**Library choice:** `PyJWT` + `cryptography` for RS256 JWT validation. Preferred over `python-jose` which is less actively maintained. `httpx` (async) for fetching JWKS and OIDC discovery.

**Validation checks:** issuer, expiration, signature, roles claim (must contain at least one role). Audience validation is disabled because Keycloak's access tokens use `aud: "account"` by default, not the client_id.

### 3. Role gating (presence check only)

The JWT access token from Keycloak contains a `roles` claim (typically under `realm_access.roles` or a custom claim path). The backend middleware checks that the decoded token contains at least one role. If the roles claim is missing or empty, the backend returns HTTP 403 with a structured error indicating the user lacks roles.

The frontend handles 403 differently from 401: instead of redirecting to login, it shows an "Access Denied" page telling the user to contact the administrator for permissions.

**Why not granular RBAC now:** All authenticated users with any role get full access. This avoids premature complexity. A future change will map specific roles to specific functionality.

**Claim path:** The exact claim path for roles will be determined by the Keycloak client configuration. The backend should support a configurable `OIDC_ROLES_CLAIM` env var (defaulting to `realm_access.roles`) to allow flexibility without code changes.

### 4. OIDC auto-discovery

The backend fetches the well-known OIDC configuration at startup from `https://id.devops-consultants.net/auth/realms/devops-consultants/.well-known/openid-configuration` to resolve all endpoints (authorization, token, JWKS, end-session). This avoids hardcoding individual endpoint URLs.

### 5. Route structure

| Path prefix | Routed to | Auth required |
|---|---|---|
| `/auth/*` | Backend | No (handles login/callback/logout) |
| `/api/*` | Backend | Yes (JWT Bearer) |
| `/api/health` | Backend | No (liveness/readiness probe) |
| `/metrics/*` | Backend (internal only) | No (KEDA polling, not exposed via ingress) |
| `/*` (default) | Frontend | No (static assets) |

### 6. Token delivery to frontend after callback

After the backend exchanges the auth code at `/auth/callback`, it redirects the browser back to the frontend root (`/`) with the access token in a URL fragment (`#access_token=...`). The frontend reads the fragment, stores the token in the Pinia auth store (memory), and clears the fragment.

**Why URL fragment:** Fragments are not sent to servers in subsequent requests, reducing leak surface. The frontend reads it client-side and removes it from the URL immediately.

**Why not a cookie:** Keeping tokens in `Authorization` headers gives explicit control and avoids CSRF concerns.

### 7. Frontend auth handling

The frontend does not need an OIDC client library. Auth logic is minimal:
- On app load: check if an access token exists in the auth store
- If no token and no URL fragment: redirect to `/auth/login`
- If URL fragment contains a token: store it, clear the fragment, proceed
- On 401 response from any API call: clear token, redirect to `/auth/login`
- On 403 response from any API call: show "Access Denied" page (user is authenticated but has no roles)
- Logout: redirect to `/auth/logout`

### 8. Environment variables

| Variable | Used by | Description |
|---|---|---|
| `OIDC_DISCOVERY_URL` | Backend | Well-known OIDC config URL |
| `OIDC_CLIENT_ID` | Backend | Keycloak client ID |
| `OIDC_CLIENT_SECRET` | Backend | Keycloak client secret |
| `OIDC_ROLES_CLAIM` | Backend | Dot-path to roles in JWT (default: `realm_access.roles`) |

The frontend needs no auth-related env vars — it interacts only with the backend's `/auth/*` routes.

## Risks / Trade-offs

**[Access token in URL fragment]** → Token is briefly visible in browser history. Mitigation: frontend clears the fragment immediately on read. For MVP this is acceptable; a future improvement could use a short-lived intermediary code.

**[No refresh token handling]** → When the access token expires, the user must re-authenticate via Keycloak (which may still have an active SSO session, making this seamless). Mitigation: acceptable for MVP; add silent refresh later if UX suffers.

**[JWKS cache staleness]** → If Keycloak rotates keys, cached keys may reject valid tokens. Mitigation: on signature validation failure, re-fetch JWKS once before returning 401.

**[Single OIDC provider dependency]** → If Keycloak is down, no one can log in. Mitigation: Keycloak availability is an infrastructure concern outside this app's scope.

**[No local Keycloak in Docker Compose]** → Local development requires network access to `id.devops-consultants.net`. Mitigation: acceptable trade-off — avoids complex local Keycloak setup. Developers need VPN/network access.
