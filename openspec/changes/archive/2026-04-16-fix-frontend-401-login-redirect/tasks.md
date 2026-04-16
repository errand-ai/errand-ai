## 1. Version and branch

- [x] 1.1 ~~Create feature branch `fix-frontend-401-login-redirect` off `main`~~ — **DEVIATION:** implemented on the existing `github-projects-integration` branch at user direction (change artifacts already lived on this branch).
- [x] 1.2 Bump `VERSION` from `0.104.0` to `0.104.1` (patch — bug fix, no API changes; tasks.md originally cited 0.69.0 but the VERSION file had advanced by the time this change was implemented)

## 2. Auth store helper

- [x] 2.1 Add `redirectToLogin()` function in `frontend/src/stores/auth.ts` that branches on `authMode.value` (`"sso"` → `window.location.href = '/auth/login'`, otherwise → `window.location.href = '/login'`)
- [x] 2.2 Export `redirectToLogin` from the store's return object so `useAuthStore()` consumers can call `auth.redirectToLogin()`

## 3. Wire the helper into 401 handlers

- [x] 3.1 In `frontend/src/composables/useApi.ts` (around line 92-93), replace `window.location.href = '/auth/login'` with `auth.redirectToLogin()` in the refresh-failure branch of `authFetch`
- [x] 3.2 In `frontend/src/main.ts` (around line 20-23), replace `window.location.href = '/auth/login'` with `auth.redirectToLogin()` inside the `onUnauthorized` callback passed to `createDirectApi`

## 4. Tests

- [x] 4.1 Update `frontend/src/composables/__tests__/useApi.test.ts`: change the assertion at line 77 from `'/auth/login'` to `'/login'` (refresh-fails case, default auth mode)
- [x] 4.2 Update the assertion at line 90 from `'/auth/login'` to `'/login'` (no-refresh-token case, default auth mode)
- [x] 4.3 Add a new test: seed the auth store with `setAuthMode('sso')`, trigger a 401 with no refresh token, and assert `window.location.href` is `/auth/login`
- [x] 4.4 Run `cd frontend && npm test` and confirm the full suite passes (332 passed; task originally said `test:run` but the actual script is `test`)
- [x] 4.5 Run `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v` to confirm no backend regressions (1338 passed)

## 5. Local verification

- [x] 5.1 Rebuild and restart the errand service: `export NPM_TOKEN=$(gh auth token) && docker compose -f testing/docker-compose.yml up -d --build errand`
- [x] 5.2 Navigate to http://localhost:8000 in Playwright; confirmed the Vue `/login` page renders (not the JSON 503)
- [x] 5.3 Logged in with `admin` / `changeme` via Playwright; Kanban board loaded (screenshot at `.playwright-mcp/fix-frontend-401-login-redirect-kanban.png`). Had to clear a stale admin row from the persisted postgres-data volume first — the auto-provision logic at `errand/main.py:211-214` only seeds when the user row is absent and does not refresh the bcrypt hash when `ADMIN_PASSWORD` changes. Orthogonal ergonomics issue, separate from this change.
- [x] 5.4 Stale-token path verified via Playwright: set `localStorage.auth_token = 'bogus'`, reloaded `/`, browser landed on `/login` (Vue page, screenshot at `.playwright-mcp/fix-frontend-401-login-redirect-verification.png`) — NOT `/auth/login` (confirmed still returns `{"detail":"OIDC authentication is not configured"}` HTTP 503 via `curl`)

## 6. Ship

- [x] 6.1 Committed (cf26003) on `github-projects-integration` with VERSION bump and OpenSpec artifacts
- [x] 6.2 Pushed to origin/github-projects-integration — branch already has an open PR from prior work; this commit rides on top. A dedicated PR for just this fix is not opened because the branch was shared at user direction.
- [x] 6.3 CI run 24501881659 passed on `cf26003` — version, test, build-task-runner, build-errand, helm all green
- [x] 6.4 Deployment validation delegated to ArgoCD auto-sync per user direction; manual `helm upgrade --dry-run` not run.
- [x] 6.5 Archiving now at user direction (before PR #105 merge); delta spec will be folded into `openspec/specs/frontend-auth/spec.md` as part of `openspec archive`.
