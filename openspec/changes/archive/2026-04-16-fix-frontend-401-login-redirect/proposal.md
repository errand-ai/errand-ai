## Why

When OIDC is not configured (e.g. local docker-compose stack with only `ADMIN_USERNAME`/`ADMIN_PASSWORD`), users loading http://localhost:8000 with a stale JWT in localStorage get redirected to `/auth/login` — the backend OIDC endpoint — which returns raw JSON `{"detail":"OIDC authentication is not configured"}`. The expected behaviour is the Vue `/login` page rendering so the user can sign in locally.

The backend is correct: `/auth/login` is an OIDC-only route by design and returns 503 when OIDC is unwired. The frontend is wrong: two 401 handlers redirect to `/auth/login` unconditionally, ignoring the current `authMode`. The spec itself is internally inconsistent — `frontend-auth` §"Handle 401 responses" hardcodes `/auth/login`, while §"Boot sequence" already says the frontend SHALL NOT redirect there blindly.

## What Changes

- Modify the `frontend-auth` capability's **Handle 401 responses** requirement so the post-refresh-failure and no-refresh-token redirect targets depend on `authMode`: `"sso"` → `/auth/login` (OIDC), otherwise → `/login` (Vue SPA route).
- Implementation: centralise the redirect in `useAuthStore` as a new `redirectToLogin()` helper; both 401 callers (`useApi.ts` and `main.ts`'s `createDirectApi` adapter) use it.

## Capabilities

### New Capabilities

<!-- None — this change only modifies an existing capability. -->

### Modified Capabilities

- `frontend-auth`: "Handle 401 responses" requirement updated so the redirect target is chosen by `authMode` instead of being hardcoded to `/auth/login`. A new scenario covers the local-mode path; existing SSO scenarios are preserved.

## Impact

- **Code**: `frontend/src/stores/auth.ts` (new exported helper), `frontend/src/composables/useApi.ts` (1 call site), `frontend/src/main.ts` (1 call site).
- **Tests**: `frontend/src/composables/__tests__/useApi.test.ts` — two assertions updated, one new SSO-branch test added.
- **Backend**: no changes. `errand/auth_routes.py` and `errand/main.py:_resolve_auth_mode()` are already correct.
- **APIs / data model / deployment**: unaffected.
