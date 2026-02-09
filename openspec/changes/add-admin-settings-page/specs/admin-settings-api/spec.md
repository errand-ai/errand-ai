## ADDED Requirements

### Requirement: Settings database table
The backend SHALL have a `settings` table with columns: `key` (text, primary key), `value` (JSONB, not null), and `updated_at` (timestamptz, not null, auto-updated). An Alembic migration SHALL create this table.

#### Scenario: Migration creates settings table
- **WHEN** the Alembic migration runs
- **THEN** a `settings` table is created with columns `key` (text PK), `value` (JSONB), and `updated_at` (timestamptz)

#### Scenario: Migration is reversible
- **WHEN** the Alembic migration is downgraded
- **THEN** the `settings` table is dropped

### Requirement: Admin role dependency
The backend SHALL provide a `require_admin` FastAPI dependency that validates the current user has the `admin` role. The dependency SHALL reuse `get_current_user` to obtain the JWT claims, extract roles using the configured roles claim path, and check that `admin` is present in the roles list.

#### Scenario: User has admin role
- **WHEN** a request includes a valid Bearer token with the `admin` role in the configured roles claim
- **THEN** the dependency returns the JWT claims and the request proceeds

#### Scenario: User lacks admin role
- **WHEN** a request includes a valid Bearer token without the `admin` role
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

#### Scenario: Unauthenticated request
- **WHEN** a request has no Authorization header
- **THEN** the backend returns HTTP 401 (handled by existing `get_current_user`)

### Requirement: Get all settings
The backend SHALL expose `GET /api/settings` requiring the `admin` role. The endpoint SHALL return a JSON object with all settings, where each key maps to its stored value. If no settings exist, the endpoint SHALL return an empty object `{}`.

#### Scenario: Settings exist
- **WHEN** an admin requests `GET /api/settings` and settings `system_prompt` and `mcp_servers` exist
- **THEN** the backend returns HTTP 200 with `{"system_prompt": "...", "mcp_servers": [...]}`

#### Scenario: No settings exist
- **WHEN** an admin requests `GET /api/settings` and the settings table is empty
- **THEN** the backend returns HTTP 200 with `{}`

#### Scenario: Non-admin user
- **WHEN** a non-admin user requests `GET /api/settings`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

### Requirement: Update settings
The backend SHALL expose `PUT /api/settings` requiring the `admin` role. The endpoint SHALL accept a JSON object where each key-value pair is upserted into the settings table. Keys not included in the request body SHALL remain unchanged. The endpoint SHALL return the full settings object after the update.

#### Scenario: Create new settings
- **WHEN** an admin sends `PUT /api/settings` with `{"system_prompt": "You are a helpful assistant"}` and no settings exist
- **THEN** the backend creates the setting and returns HTTP 200 with the full settings object

#### Scenario: Update existing setting
- **WHEN** an admin sends `PUT /api/settings` with `{"system_prompt": "Updated prompt"}` and `system_prompt` already exists
- **THEN** the backend updates the value and returns HTTP 200 with the full settings object

#### Scenario: Partial update preserves other settings
- **WHEN** an admin sends `PUT /api/settings` with `{"system_prompt": "New"}` and `mcp_servers` also exists
- **THEN** the `mcp_servers` setting is unchanged and both appear in the response

#### Scenario: Non-admin user
- **WHEN** a non-admin user sends `PUT /api/settings`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

### Requirement: Settings endpoints exempt from general role check
The `/api/settings` endpoints SHALL use the `require_admin` dependency instead of the general `get_current_user` dependency. The `require_admin` dependency SHALL still validate the JWT and require authentication, but SHALL allow users with the `admin` role even if they have no other roles.

#### Scenario: Admin-only user accesses settings
- **WHEN** a user with only the `admin` role (and no other roles) requests `GET /api/settings`
- **THEN** the request succeeds with HTTP 200
