## Context

The frontend has two independent 401 handlers: the legacy `authFetch` helper in `frontend/src/composables/useApi.ts` and the newer `onUnauthorized` callback wired into `@errand-ai/ui-components`' `createDirectApi` at `frontend/src/main.ts`. Both clear the auth store and then set `window.location.href = '/auth/login'`.

`App.vue`'s `onMounted` boot sequence already branches on `authMode` correctly (local → Vue `/login`, sso → `/auth/login`), but it only runs once on initial load. Later 401s (stale localStorage token after a dev-stack rebuild is the common trigger) bypass it and hit the hardcoded redirect.

The `frontend-auth` spec is self-contradictory: §"Boot sequence" line 28 states "The frontend SHALL NOT redirect to `/auth/login` blindly", yet §"Handle 401 responses" scenarios prescribe the blind redirect.

## Goals / Non-Goals

**Goals:**
- `/auth/login` (backend OIDC redirect) is only used when the app is actually in SSO mode.
- A single, testable place owns the "redirect to login" policy.
- Spec and implementation agree.

**Non-Goals:**
- Changing the boot-time auth mode detection in `App.vue`.
- Changing the backend's 503 behaviour for `/auth/login` — that route is OIDC-only and the 503 is correct.
- Handling `authMode === 'setup'` specially at the 401 sites — the setup wizard is reached via boot-time routing, and a user who is already authenticated enough to receive a 401 should not be in setup mode.

## Decisions

**Decision 1 — Centralise the redirect in `useAuthStore` as `redirectToLogin()`.**

Rationale: both 401 callers already depend on the store (they call `auth.clearToken()` immediately before the redirect), and the store already owns `authMode`. A sibling method is the minimum-surface change. Consumers call `auth.redirectToLogin()` and neither caller needs to know about `authMode` or the OIDC/local branching.

Alternatives considered:
- *Inline the branch at each call site.* Rejected — duplicates the `authMode` check; easy for a future third caller (e.g. a new WebSocket reconnect handler) to forget and regress the bug.
- *Handle it in a Vue-Router navigation guard.* Rejected — the 401 handlers already decided to use `window.location.href` (full reload) rather than router navigation, and flipping to router navigation is a larger change that would complicate the SSO path (which must be a full navigation to the backend).

**Decision 2 — Branch: `authMode === 'sso'` → `/auth/login`, otherwise → `/login`.**

Rationale: `/login` is the Vue route that renders `LoginPage.vue` for local auth. It also works as a safe default when `authMode` is still `null` (e.g. a 401 fires before the initial `/api/auth/status` response returns): the SPA fallback at `errand/main.py:2509` serves `index.html`, App.vue boots, fetches status, and takes the correct branch. `/auth/login` as the default would land on the backend OIDC route and surface the same JSON error.

Alternatives considered:
- *Redirect to `/` and let `App.vue` decide.* Equivalent net effect, but adds a round-trip through the Kanban route guard and is harder to test.
- *Honour `authMode === 'setup'` → `/setup`.* Unnecessary: a user holding a token that produces 401 is past the setup gate; if they somehow regress to setup mode, the App.vue boot redirect will still send them to `/setup`.

## Risks / Trade-offs

- **Risk:** `authMode` is `null` when the 401 fires (status fetch hasn't returned yet). → Mitigation: the else-branch targets `/login`, which triggers a full reload; the subsequent App.vue boot will fetch status and redirect again if needed (setup/sso). No user-visible dead end.
- **Risk:** A third party (e.g. a future SDK adapter) adds a new 401 handler and forgets to use the helper. → Mitigation: the helper is exported from the store and the spec now names `authMode`-driven redirection as the requirement; code review and tests catch future regressions.
- **Trade-off:** `redirectToLogin()` reads `authMode.value` at call time, not when the store was initialised. This is desired (mode can change during a session, e.g. after setup completes) but means tests must set the mode explicitly.
