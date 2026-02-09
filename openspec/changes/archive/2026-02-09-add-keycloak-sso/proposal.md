## Why

The app currently has no authentication — all API endpoints and the frontend are fully open. Before deploying to Kubernetes, we need to gate access behind SSO so only authenticated users from the organization can use the app. Keycloak is already running at `id.devops-consultants.net` and provides OIDC, so we integrate with it rather than building our own auth.

## What Changes

- Add OIDC-based authentication to the **backend** using Keycloak as the identity provider (Authorization Code flow)
- Backend handles the full OIDC login flow: `/auth/login` initiates redirect to Keycloak, `/auth/callback` handles the code exchange and issues a session/token
- Backend validates JWT access tokens on all `/api/` endpoints (except `/api/health`)
- Frontend redirects unauthenticated users to `/auth/login`, receives tokens after callback, sends `Authorization: Bearer <token>` on API requests
- Add logout support (`/auth/logout` clears session + redirects to Keycloak end-session)
- Move KEDA worker metrics to `/metrics/queue` (unauthenticated, not exposed via ingress)
- **BREAKING**: All `/api/*` endpoints require a valid Bearer token with at least one role in the roles claim
- Users with valid tokens but no roles see an "Access Denied" page directing them to contact the administrator
- **BREAKING**: Queue metrics endpoint moves from `/api/metrics/queue` to `/metrics/queue`
- Add Keycloak config to Helm chart (client ID, client secret via Kubernetes Secret)
- Add path-based ingress routing: default → frontend, `/api` + `/auth` → backend, `/metrics` not exposed
- Add Keycloak config to Docker Compose for local development

## Capabilities

### New Capabilities

- `keycloak-auth`: Backend OIDC integration — `/auth/*` routes for login/callback/logout, JWT validation middleware, JWKS key fetching, protected `/api/*` routes
- `frontend-auth`: Frontend auth state management — redirect to `/auth/login` when unauthenticated, token storage, authenticated API requests, show current user, logout button

### Modified Capabilities

- `task-api`: All `/api/*` endpoints require Bearer token authentication; queue metrics move to `/metrics/queue` (unauthenticated)
- `kanban-frontend`: UI must handle auth state (redirect to login, show current user, logout button)
- `helm-deployment`: Add path-based ingress routing (default → frontend, `/api` + `/auth` → backend), add Keycloak secret reference and environment variables to backend deployment
- `local-dev-environment`: Add Keycloak environment variables to Docker Compose services

## Impact

- **Routing**: Single FQDN in K8s with path-based ingress routing. Default path → frontend, `/api` and `/auth` → backend. `/metrics` is backend-only and not exposed via ingress (used internally by KEDA).
- **Backend**: New dependencies for JWT validation and OIDC (`python-jose[cryptography]` or `PyJWT`, `httpx` for JWKS). New `/auth/*` routes. Auth middleware on all `/api/*` routes. `/api/health` remains unauthenticated.
- **Frontend**: Minimal auth changes — no OIDC library needed since backend handles the flow. New Pinia auth store for token state, fetch/axios interceptor for Bearer header, login redirect logic.
- **Helm chart**: New `keycloak` section in `values.yaml` referencing a Kubernetes Secret for `CLIENT_ID` and `CLIENT_SECRET`. Ingress updated with path-based routing rules.
- **Docker Compose**: Backend service gets `KEYCLOAK_*` / `OIDC_*` environment variables (`CLIENT_ID`, `CLIENT_SECRET`, well-known URL).
- **CI/CD**: No pipeline changes — existing build workflow covers new dependencies.
- **OIDC Provider**: Keycloak at `https://id.devops-consultants.net/auth/realms/devops-consultants/` (well-known config endpoint for auto-discovery).
