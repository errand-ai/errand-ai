## Context

The content-manager currently has a flat authorization model: any user with at least one Keycloak client role can access all features. There is no admin concept, no settings persistence, and no Vue Router — the app renders conditionally in a single `App.vue`. The backend `get_current_user` dependency extracts roles from the JWT but discards them (only checks that at least one exists).

Recent additions: the backend now uses Valkey pub/sub for real-time WebSocket task events (`/api/ws/tasks`), and the frontend uses a `useTaskStore` + `useWebSocket` composable that manages WebSocket lifecycle in `KanbanBoard`'s `onMounted`/`onUnmounted`. The `docker-compose.yml` includes a Valkey service.

This change introduces admin-only functionality for the first time, requiring: role awareness in the frontend, a new routing layer, a new database table, and role-gated API endpoints.

## Goals / Non-Goals

**Goals:**
- Establish the admin role pattern (frontend + backend) as a reusable foundation
- Add a settings page with placeholder UI for system prompt and MCP server config
- Persist settings in the database so they survive restarts
- Gate all settings access behind the `admin` role on both frontend and backend

**Non-Goals:**
- Implementing the actual LLM/MCP integration (future change)
- Building a full RBAC framework — this is a single `admin` role check
- Adding settings import/export, versioning, or audit logging
- Changing the Keycloak configuration (admin role must be manually assigned in Keycloak)

## Decisions

### 1. Frontend routing: Vue Router

**Decision**: Add `vue-router` to the frontend and convert `App.vue` from conditional rendering to route-based navigation.

**Rationale**: The app now has two distinct pages (kanban board and settings). Vue Router is the standard solution for Vue 3 SPAs and enables route guards for role-gating. The alternative (more conditional rendering in App.vue) doesn't scale and makes deep-linking impossible.

**Impact**: `App.vue` changes from `<KanbanBoard v-else />` / `<AccessDenied v-if="auth.accessDenied" />` to `<router-view />`. The header and auth logic remain in App.vue as the layout shell. The `AccessDenied` state should be handled as a layout-level concern (rendered above `<router-view>` when active). Two routes: `/` (kanban) and `/settings` (admin-only). Note: `KanbanBoard` manages WebSocket lifecycle via `onMounted`/`onUnmounted` — route transitions must preserve clean mount/unmount behavior.

### 2. Role extraction in the frontend: decode JWT claims client-side

**Decision**: Extract roles from the JWT payload in the auth store using the same claim path (`resource_access.content-manager.roles`) the backend uses.

**Rationale**: The access token is already available in the frontend. Decoding the payload (base64, no signature verification needed — the backend validates the token) gives us roles without an extra API call. The alternative (a `/api/me` endpoint) adds latency and complexity for information already in the token.

**Trade-off**: If the roles claim path changes, both frontend and backend must be updated. This is acceptable since the path is already a backend env var (`OIDC_ROLES_CLAIM`) and rarely changes.

### 3. Admin dropdown: replace username area for admins only

**Decision**: For admin users, replace the static "username + logout button" with a dropdown menu containing "Settings" and "Log out". Non-admin users keep the existing layout unchanged.

**Rationale**: Minimal visual disruption. The dropdown only appears for admins, so regular users see no change. A dedicated nav bar or sidebar would be overbuilt for a single additional page.

### 4. Settings storage: single `settings` table with key-value rows

**Decision**: Create a `settings` table with columns: `key` (text, primary key), `value` (JSONB), `updated_at` (timestamptz). Each setting is a row identified by its key (e.g., `system_prompt`, `mcp_servers`).

**Rationale**: A key-value approach is flexible — new setting types can be added without schema migrations. JSONB for the value column allows structured data (e.g., MCP server configs as arrays of objects) while keeping a single table. The alternative (one column per setting) requires a migration for every new setting type.

**Keys defined in this change**:
- `system_prompt` — string value (the LLM system prompt text)
- `mcp_servers` — JSON array of server configuration objects (placeholder structure)

### 5. Backend role gating: `require_admin` FastAPI dependency

**Decision**: Create a `require_admin` FastAPI dependency that independently validates the JWT and checks for the `admin` role. It does not wrap `get_current_user` — it performs its own token decoding and role extraction, then checks that `admin` is present. Apply it to all `/api/settings` endpoints.

**Rationale**: An independent dependency avoids inheriting `get_current_user`'s "no roles → 403" rejection, which would incorrectly block a user whose only role is `admin`. It also keeps the admin gate self-contained and reusable for future admin-only endpoints without coupling to the general auth dependency's behavior.

### 6. Settings API: GET/PUT on `/api/settings`

**Decision**: Two endpoints:
- `GET /api/settings` — returns all settings as a JSON object `{ "system_prompt": "...", "mcp_servers": [...] }`
- `PUT /api/settings` — accepts a partial or full JSON object and upserts each key

**Rationale**: A single GET returns everything (the settings payload is small). PUT with upsert semantics is idempotent and handles both initial creation and updates. Individual `GET/PUT /api/settings/{key}` endpoints could be added later if needed but aren't necessary now.

## Risks / Trade-offs

- **[Risk] JWT roles claim path hardcoded in frontend** → Acceptable for now; if it changes, both frontend and backend need updating. Could be made configurable via a build-time env var in the future.
- **[Risk] No input validation on settings values** → The placeholder UI doesn't enforce structure. Future changes that wire up LLM/MCP functionality will need to validate the settings values they consume.
- **[Risk] No settings change audit trail** → Acceptable for initial implementation. Can add `updated_by` column and history table in a future change if needed.
- **[Trade-off] Vue Router added as a dependency** → Increases bundle size slightly but is necessary for multi-page navigation and is the standard Vue 3 approach.

## Migration Plan

1. **Database**: Alembic migration adds the `settings` table. Non-destructive — no existing tables are modified.
2. **Backend**: New endpoints and dependency added. Existing endpoints unchanged. The `get_current_user` dependency now also returns roles in the claims dict (it already does — they're in the JWT, just not explicitly extracted).
3. **Frontend**: Vue Router added, App.vue refactored to use `<router-view>`. Header gains dropdown for admins. New SettingsPage component added.
4. **Rollback**: Remove the migration (downgrade), revert frontend/backend code. No data loss since the `settings` table is new.
5. **Keycloak**: The `admin` role must exist in the `content-manager` client roles. This is a manual one-time setup — assign the role to admin users.
