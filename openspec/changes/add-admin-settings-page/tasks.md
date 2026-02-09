## 1. Database & Backend Foundation

- [x] 1.1 Create Alembic migration adding `settings` table (columns: `key` text PK, `value` JSONB not null, `updated_at` timestamptz not null)
- [x] 1.2 Add `Setting` SQLAlchemy model in `models.py`
- [x] 1.3 Add `require_admin` FastAPI dependency in `main.py` that wraps `get_current_user`, extracts roles via `oidc.extract_roles()`, and returns 403 if `admin` not present

## 2. Settings API Endpoints

- [x] 2.1 Add `GET /api/settings` endpoint using `require_admin` dependency — returns all settings as `{key: value}` object, or `{}` if none exist
- [x] 2.2 Add `PUT /api/settings` endpoint using `require_admin` dependency — accepts JSON object, upserts each key-value pair, returns full settings object
- [x] 2.3 Add backend tests for settings endpoints (admin access, non-admin 403, GET empty, PUT create, PUT update, partial update preserves other keys)

## 3. Frontend Auth Store

- [x] 3.1 Add `roles` computed to auth store — extracts `resource_access.content-manager.roles` from JWT payload, returns `[]` on failure
- [x] 3.2 Add `isAdmin` computed to auth store — returns `true` if `roles` includes `"admin"`
- [x] 3.3 Add frontend tests for `roles` and `isAdmin` computeds (token with roles, token without roles claim, no token)

## 4. Vue Router Setup

- [x] 4.1 Install `vue-router` dependency
- [x] 4.2 Create router config (`src/router/index.ts`) with routes: `/` → KanbanBoard, `/settings` → SettingsPage
- [x] 4.3 Add `beforeEach` navigation guard on `/settings` route — redirect to `/` if `isAdmin` is false
- [x] 4.4 Refactor `App.vue` to use `<router-view>` in place of direct `<KanbanBoard>` / `<AccessDenied>` rendering. Keep `AccessDenied` as a layout-level concern above `<router-view>`. Ensure `KanbanBoard` WebSocket lifecycle (`store.start()`/`store.stop()` in `onMounted`/`onUnmounted`) works correctly with route transitions
- [x] 4.5 Update `main.ts` to register the router plugin

## 5. Admin Header Dropdown

- [x] 5.1 Add admin dropdown menu to `App.vue` header — triggered by clicking username, contains "Settings" link and "Log out" action
- [x] 5.2 Keep existing static username + logout button for non-admin users (conditional rendering based on `isAdmin`)
- [x] 5.3 Add click-outside handler to close dropdown
- [x] 5.4 Add frontend tests for admin dropdown visibility (admin sees dropdown, non-admin sees static layout)

## 6. Settings Page

- [x] 6.1 Create `SettingsPage.vue` component with heading and two card sections ("System Prompt" and "MCP Server Configuration")
- [x] 6.2 Add system prompt textarea that loads value from `GET /api/settings` on mount and saves via `PUT /api/settings` on button click
- [x] 6.3 Add MCP server configuration placeholder section — shows descriptive text and read-only formatted JSON if `mcp_servers` value exists
- [x] 6.4 Add error handling — display error messages for API failures, show "Access denied" message on 403
- [x] 6.5 Add frontend tests for settings page (renders sections, loads settings, saves system prompt, handles errors)

## 7. Verification

- [x] 7.1 Run full backend test suite (`pytest`) — all tests pass
- [x] 7.2 Run full frontend test suite (`vitest`) — all tests pass
- [x] 7.3 Run `docker compose up --build` and verify end-to-end: admin user sees dropdown, navigates to settings, saves a system prompt; non-admin user sees no dropdown and cannot access `/settings` *(requires OIDC env vars + Keycloak admin role setup — manual verification)* — **Verified non-admin e2e**: static layout, /settings redirect, API 403. Admin flow verified by unit tests only (test user lacks admin role in Keycloak).
