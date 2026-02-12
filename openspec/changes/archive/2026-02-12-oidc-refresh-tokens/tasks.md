## 1. Backend — Login and Callback Changes

- [x] 1.1 Add `offline_access` to the scope parameter in the `/auth/login` endpoint
- [x] 1.2 Update `/auth/callback` to include `refresh_token` in the URL fragment redirect (only if present in Keycloak response)
- [x] 1.3 Update backend auth tests for login scope and callback refresh token passthrough

## 2. Backend — Refresh Endpoint

- [x] 2.1 Add `POST /auth/refresh` endpoint that accepts `{"refresh_token": "..."}`, exchanges with Keycloak token endpoint using `client_id`/`client_secret` and `grant_type=refresh_token`, returns new tokens as JSON
- [x] 2.2 Handle error cases: missing refresh_token (400), expired/revoked token (401), Keycloak unreachable (502)
- [x] 2.3 Add backend tests for the refresh endpoint (success, expired token, missing field, upstream failure)

## 3. Frontend — Auth Store Changes

- [x] 3.1 Add `refreshToken` ref to the auth store, update `setToken` to accept optional refresh token parameter, update `clearToken` to clear it
- [x] 3.2 Add refresh timer logic: decode `exp` from access token, schedule `setTimeout` for 30 seconds before expiry, call `/auth/refresh`, update tokens on success, cancel timer on `clearToken`
- [x] 3.3 Update frontend auth store tests for refresh token state management and timer scheduling

## 4. Frontend — Token Extraction and API Layer

- [x] 4.1 Update `App.vue` token extraction to parse `refresh_token` from the URL fragment and pass it to `setToken`
- [x] 4.2 Update `authFetch` in `useApi.ts`: on 401, attempt `POST /auth/refresh` if refresh token available, update store, retry original request once; fall back to login redirect if refresh fails or no refresh token
- [x] 4.3 Update frontend API/integration tests for 401 retry-after-refresh behaviour

## 5. Version Bump and Verification

- [x] 5.1 Bump VERSION file (minor version increment)
- [x] 5.2 Run full test suite (`pytest` + `vitest`) and verify all tests pass
