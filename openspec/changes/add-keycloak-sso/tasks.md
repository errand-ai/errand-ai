## 1. Backend Dependencies and Configuration

- [x] 1.1 Add `PyJWT`, `cryptography`, and `httpx` to `backend/requirements.txt`
- [x] 1.2 Create `backend/auth.py` module with OIDC config dataclass reading `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ROLES_CLAIM` (default `realm_access.roles`) from environment variables; fail on missing required vars
- [x] 1.3 Implement OIDC discovery function in `backend/auth.py` that fetches the well-known config URL and caches authorization endpoint, token endpoint, JWKS URI, and end-session endpoint

## 2. Backend JWKS and JWT Validation

- [x] 2.1 Implement JWKS fetcher in `backend/auth.py` — fetch public keys from JWKS URI, cache in memory, re-fetch on unknown `kid`
- [x] 2.2 Implement JWT validation function — verify signature (RS256 via JWKS), issuer, audience (client_id), expiration; extract and return decoded claims
- [x] 2.3 Implement roles extraction — read roles from the configured dot-path claim; return the roles list (may be empty)

## 3. Backend Auth Routes

- [x] 3.1 Create `backend/auth_routes.py` with a FastAPI router mounted at `/auth`
- [x] 3.2 Implement `GET /auth/login` — redirect to Keycloak authorization endpoint with `client_id`, `redirect_uri`, `response_type=code`, `scope=openid`
- [x] 3.3 Implement `GET /auth/callback` — receive auth code, exchange for tokens via Keycloak token endpoint using `client_id` + `client_secret`, redirect to `/#access_token=<token>` on success; return 401 on invalid code or Keycloak error
- [x] 3.4 Implement `GET /auth/logout` — redirect to Keycloak end-session endpoint with `post_logout_redirect_uri=/`

## 4. Backend Auth Middleware

- [x] 4.1 Create FastAPI dependency (`get_current_user`) that extracts and validates the Bearer token from the Authorization header; returns 401 if missing/invalid/expired
- [x] 4.2 Add roles check to `get_current_user` — return 403 with `"No roles assigned. Contact your administrator for access."` if roles claim is empty or missing
- [x] 4.3 Apply `get_current_user` dependency to all `/api/*` routes except `/api/health`

## 5. Backend Metrics Endpoint Move

- [x] 5.1 Move queue metrics endpoint from `GET /api/metrics/queue` to `GET /metrics/queue` (no auth required)
- [x] 5.2 Register the `/auth` router and `/metrics` routes in `backend/main.py`; run OIDC discovery in the app lifespan startup

## 6. Frontend Auth Store

- [x] 6.1 Create `frontend/src/stores/auth.ts` — Pinia store with `token`, `isAuthenticated` computed, `setToken()`, `clearToken()` actions
- [x] 6.2 Implement token extraction from URL fragment on app load — parse `#access_token=...`, call `setToken()`, clear fragment from URL

## 7. Frontend Auth Flow

- [x] 7.1 Add auth guard in `frontend/src/App.vue` (or a composable) — redirect to `/auth/login` when no token is present and no fragment found
- [x] 7.2 Update `frontend/src/composables/useApi.ts` to include `Authorization: Bearer <token>` header on all `/api/*` requests
- [x] 7.3 Add 401 response interceptor — clear token and redirect to `/auth/login`
- [x] 7.4 Add 403 response interceptor — set an `accessDenied` flag in the auth store

## 8. Frontend Access Denied Page

- [x] 8.1 Create `frontend/src/components/AccessDenied.vue` — display message "You do not have permission to access this application. Please contact your administrator." with a logout button
- [x] 8.2 Render `AccessDenied` component when `accessDenied` is true in the auth store (instead of the Kanban board)

## 9. Frontend User Display and Logout

- [x] 9.1 Decode the JWT access token client-side to extract user name/email from claims; expose via auth store
- [x] 9.2 Add user identity display and logout button to the app header in `App.vue` or a new header component
- [x] 9.3 Implement logout action — navigate to `/auth/logout`

## 10. Nginx Configuration

- [x] 10.1 Update `frontend/nginx.conf` to proxy `/auth/*` requests to the backend service (in addition to existing `/api/*` proxy)

## 11. Docker Compose

- [x] 11.1 Add `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` environment variables to the backend service in `docker-compose.yml` using `${VAR}` syntax for `.env` file support
- [x] 11.2 Create a `.env.example` file documenting the required OIDC variables

## 12. Helm Chart

- [x] 12.1 Add `keycloak` section to `helm/content-manager/values.yaml` — `existingSecret`, `secretKeyClientId`, `secretKeyClientSecret`, `discoveryUrl`, `rolesClaim`
- [x] 12.2 Update backend Deployment template to mount `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` from the Keycloak secret, and set `OIDC_DISCOVERY_URL` and `OIDC_ROLES_CLAIM` from values
- [x] 12.3 Update KEDA ScaledObject trigger URL from `/api/metrics/queue` to `/metrics/queue`
- [x] 12.4 Update Ingress template — add path-based routing: `/api` and `/auth` → backend service, default → frontend service; do not expose `/metrics`

## 13. Local Verification

- [x] 13.1 Run `docker compose up --build` and verify: backend starts with OIDC discovery, `/auth/login` redirects to Keycloak, callback returns token, `/api/tasks` requires Bearer token, `/metrics/queue` is accessible without auth
- [x] 13.2 Verify frontend: unauthenticated user is redirected to login, authenticated user sees Kanban board with user identity and logout button, user with no roles sees Access Denied page
