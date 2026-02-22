## 1. Database & Models

- [ ] 1.1 Add `LocalUser` model to `models.py` with columns: id, username, password_hash, role, created_at
- [ ] 1.2 Create Alembic migration for `local_users` table
- [ ] 1.3 Add `bcrypt` and `passlib` to `requirements.txt`

## 2. Settings Registry

- [ ] 2.1 Create `settings_registry.py` module with the settings definition dict mapping each known setting to env var name, sensitive flag, and default value
- [ ] 2.2 Add `resolve_settings()` function that merges env vars, DB values, and defaults into the metadata-enriched format (`{key: {value, source, sensitive, readonly}}`)
- [ ] 2.3 Add `mask_sensitive_value()` helper (first 4 chars + `****` for env-sourced sensitive values)
- [ ] 2.4 Refactor `GET /api/settings` to use the settings registry and return the new response format
- [ ] 2.5 Refactor `PUT /api/settings` to silently ignore readonly (env-sourced) keys
- [ ] 2.6 Exclude `ssh_private_key` and `jwt_signing_secret` from the settings API response
- [ ] 2.7 Register OIDC settings in the registry: `oidc_discovery_url`, `oidc_client_id`, `oidc_client_secret`, `oidc_roles_claim`
- [ ] 2.8 Register LLM settings in the registry: `openai_base_url`, `openai_api_key`

## 3. Local Auth Backend

- [ ] 3.1 Add JWT signing secret auto-generation on startup (64-char hex string stored as `jwt_signing_secret` setting)
- [ ] 3.2 Implement `POST /auth/local/login` — validate credentials, return JWT with `sub`, `email`, `_roles`, `iss: "errand-local"`, 24h expiry
- [ ] 3.3 Implement `GET /auth/local/logout` — return redirect to `/`
- [ ] 3.4 Implement `POST /auth/local/change-password` — validate current password, update hash
- [ ] 3.5 Implement `ADMIN_USERNAME`/`ADMIN_PASSWORD` env var auto-provisioning in `lifespan()`

## 4. Auth Mode Detection

- [ ] 4.1 Implement `GET /api/auth/status` endpoint (unauthenticated) returning `{mode, login_url?}`
- [ ] 4.2 Auth mode resolution logic: OIDC env → OIDC DB → local user exists → setup mode
- [ ] 4.3 Ensure `/api/auth/status` queries live state on each request (no caching)

## 5. JWT Validation Refactor

- [ ] 5.1 Refactor `get_current_user` to support both OIDC tokens (JWKS) and local tokens (HMAC) based on `iss` claim
- [ ] 5.2 Remove `_ANONYMOUS_CLAIMS` fallback — unauthenticated requests get 401

## 6. OIDC Config from DB

- [ ] 6.1 Refactor `OIDCConfig.from_env()` to also check DB settings when env vars are missing
- [ ] 6.2 Make OIDC discovery failure non-fatal at startup (log error, fall back to local auth)
- [ ] 6.3 Implement hot-reload endpoint: when OIDC settings are saved via `PUT /api/settings`, perform discovery and atomically swap the module-level `oidc` variable
- [ ] 6.4 If hot-reload discovery fails, return error to client and preserve existing auth mode

## 7. LLM Config from DB

- [ ] 7.1 Refactor `get_llm_client()` to use settings registry resolution (env var → DB → unconfigured)
- [ ] 7.2 Refactor `GET /api/llm/models` to use settings registry resolution for LLM client init
- [ ] 7.3 Return HTTP 503 from `/api/llm/models` when LLM provider is not configured via either source
- [ ] 7.4 Ensure worker reads LLM config from DB at task processing time (uses same resolution)

## 8. Setup Wizard Backend

- [ ] 8.1 Implement `POST /api/setup/create-user` — unauthenticated, guarded by zero-users check, returns JWT
- [ ] 8.2 Return 403 from create-user if any local user already exists

## 9. Frontend Settings Page Update

- [x] 9.1 Update settings store/composable to handle the new metadata-enriched response format (`{value, source, sensitive, readonly}`)
- [x] 9.2 Update all settings input components to display lock icon and "Set via environment variable" tooltip for readonly fields
- [x] 9.3 Update sensitive env-sourced fields to display the masked value and be disabled
- [x] 9.4 Add "User Management" as 5th sidebar nav item in `SettingsPage.vue`

## 10. User Management Sub-Page

- [x] 10.1 Create `UserManagementSettings.vue` component with Authentication Mode and Local Admin Account sections
- [x] 10.2 Implement OIDC configuration fields (Discovery URL, Client ID, Client Secret, Roles Claim) with read-only/lock support for env-sourced values
- [x] 10.3 Implement "Test Connection" button for OIDC discovery validation
- [x] 10.4 Implement "Save & Enable SSO" button that saves OIDC settings and triggers hot-reload
- [x] 10.5 Implement "Remove SSO" button (only shown for DB-sourced SSO config)
- [x] 10.6 Implement Local Admin Account section with username display and "Change Password" form

## 11. Frontend Auth Refactor

- [x] 11.1 Add `authMode` state and `setAuthMode()` action to the Pinia auth store
- [x] 11.2 Rewrite `App.vue` boot sequence: call `GET /api/auth/status` first, route based on mode
- [x] 11.3 Implement `/login` route with local login form (username + password)
- [x] 11.4 Update logout action to adapt based on auth mode (SSO → `/auth/logout`, local → clear store + navigate to `/login`)
- [x] 11.5 Update router guards: `/login` only accessible in local mode, redirect to SSO login in SSO mode

## 12. Setup Wizard Frontend

- [x] 12.1 Create `SetupWizard.vue` page component with 3-step stepper UI
- [x] 12.2 Implement Step 1: Create Admin Account form (username, password, confirm password) calling `POST /api/setup/create-user`
- [x] 12.3 Implement Step 2: LLM Provider Configuration form (URL, API Key) with pre-fill from env vars, read-only for env-sourced, "Test Connection" button
- [x] 12.4 Implement Step 3: Model Selection dropdowns populated from `GET /api/llm/models`, "Complete Setup" saves and redirects to `/settings`
- [x] 12.5 Add `/setup` route, accessible only in setup mode, redirects to `/` otherwise

## 13. Router & Navigation

- [x] 13.1 Add `/settings/users` child route under `/settings` with admin guard
- [x] 13.2 Add `/login` route (no auth required, local mode only)
- [x] 13.3 Add `/setup` route (no auth required, setup mode only)
- [x] 13.4 Update `/settings` redirect to still default to `/settings/agent`

## 14. Docker Compose

- [ ] 14.1 Add `ADMIN_USERNAME` and `ADMIN_PASSWORD` env vars to the errand service in `docker-compose.yml`

## 15. Backend Tests

- [ ] 15.1 Test settings registry resolution (env → DB → default) and sensitive value masking
- [ ] 15.2 Test `GET /api/settings` returns metadata-enriched format
- [ ] 15.3 Test `PUT /api/settings` ignores readonly keys
- [ ] 15.4 Test `POST /auth/local/login` — success, invalid password, unknown user
- [ ] 15.5 Test `POST /auth/local/change-password` — success, wrong current password
- [ ] 15.6 Test `GET /api/auth/status` — setup mode, local mode, SSO mode
- [ ] 15.7 Test `POST /api/setup/create-user` — success, 403 when user exists
- [ ] 15.8 Test `get_current_user` validates both OIDC and local JWTs
- [ ] 15.9 Test `ADMIN_USERNAME`/`ADMIN_PASSWORD` auto-provisioning
- [ ] 15.10 Test LLM client resolution from DB settings
- [ ] 15.11 Test OIDC hot-reload on settings save

## 16. Frontend Tests

- [x] 16.1 Test auth store `authMode` state management
- [x] 16.2 Test boot sequence routes correctly for each auth mode
- [x] 16.3 Test login page form submission and error handling
- [x] 16.4 Test setup wizard step navigation and API calls
- [x] 16.5 Test settings fields display read-only/lock for env-sourced values
- [x] 16.6 Test User Management page OIDC configuration form
