## Why

The content-manager needs a way for administrators to configure runtime settings — such as LLM system prompts and MCP server connections — without redeploying. Currently there is no admin interface and no mechanism to persist application-level configuration. Adding a role-gated settings page provides a secure foundation for managing these settings, starting with placeholders that will be wired up in future changes.

## What Changes

- Add a `roles` computed property to the frontend auth store, extracted from the JWT claims (using the same `resource_access.content-manager.roles` path the backend uses)
- Add an `isAdmin` computed to the auth store that checks for the `admin` role
- Replace the static username + logout button in the header with a dropdown menu for admin users, containing a link to the settings page and the logout action
- Add a `/settings` route (Vue Router) that is only accessible to admin users; non-admin users are redirected back to the kanban board
- Create a Settings page component with placeholder sections for "System Prompt" (textarea) and "MCP Server Configuration" (structured form placeholder)
- Add backend API endpoints (`GET /api/settings`, `PUT /api/settings`) for reading and writing settings, restricted to users with the `admin` role
- Add a `settings` database table to persist key-value configuration (Alembic migration)
- Add backend role-checking utility that extracts roles from the JWT claims already available in the auth middleware

## Capabilities

### New Capabilities
- `admin-settings-api`: Backend API endpoints for reading and writing admin settings, with role-based access control requiring the `admin` role. Includes the database model and migration for persisting settings.
- `admin-settings-ui`: Frontend settings page with role-gated routing, admin dropdown menu in the header, and placeholder UI for system prompt and MCP server configuration.

### Modified Capabilities
- `frontend-auth`: Add `roles` and `isAdmin` computed properties to the auth store, derived from JWT claims.
- `kanban-frontend`: Replace the static username display and logout button in the header with a dropdown menu for admin users (non-admin users retain the current layout).

## Impact

- **Frontend**: New Vue Router route, new Settings page component, modified header component, extended auth store
- **Backend**: New `/api/settings` endpoints, new role-checking middleware/dependency, new `settings` SQLAlchemy model
- **Database**: New Alembic migration adding a `settings` table
- **Auth**: No changes to Keycloak or OIDC flow — the `admin` role must be assigned to users in Keycloak's client role configuration for `content-manager`
- **Deployment**: No new environment variables or infrastructure changes required
