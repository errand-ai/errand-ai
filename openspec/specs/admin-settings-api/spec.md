## Purpose

Backend API for managing application settings via a key-value store with admin role protection.

## Requirements

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
The backend SHALL expose `GET /api/settings` requiring the `admin` role. The endpoint SHALL return a JSON object where each key maps to an object containing `value`, `source` (`"env"`, `"database"`, or `"default"`), `sensitive` (boolean), and `readonly` (boolean). The response SHALL include all settings known to the settings registry, regardless of whether they have a stored value. The `ssh_private_key` and `jwt_signing_secret` settings SHALL be excluded from the response. Sensitive env-sourced values SHALL be masked (first 4 characters + `****`).

#### Scenario: Settings with mixed sources
- **WHEN** an admin requests `GET /api/settings` and `OPENAI_API_KEY` env var is set, `llm_model` is in the DB, and `system_prompt` uses the default
- **THEN** the response includes all three with their respective sources, sensitivity, and readonly flags

#### Scenario: Sensitive env-sourced value masked
- **WHEN** an admin requests `GET /api/settings` and `OPENAI_API_KEY` is set to `sk-proj-abc123`
- **THEN** the `openai_api_key` entry has `"value": "sk-p****"`, `"source": "env"`, `"sensitive": true`, `"readonly": true`

#### Scenario: DB-sourced sensitive value shown in full
- **WHEN** an admin requests `GET /api/settings` and `openai_api_key` is stored in the DB as `sk-proj-abc123`
- **THEN** the entry has `"value": "sk-proj-abc123"`, `"source": "database"`, `"sensitive": true`, `"readonly": false`

#### Scenario: SSH private key excluded
- **WHEN** an admin requests `GET /api/settings` and `ssh_private_key` exists in the database
- **THEN** the response does NOT include the `ssh_private_key` key

#### Scenario: No settings exist
- **WHEN** an admin requests `GET /api/settings` and no DB settings exist and no env vars are set
- **THEN** the response includes registry-defined settings with `source: "default"` and their default values

### Requirement: Update settings
The backend SHALL expose `PUT /api/settings` requiring the `admin` role. The endpoint SHALL accept a JSON object where each key-value pair is upserted into the settings table. Keys whose values are sourced from environment variables (readonly) SHALL be silently ignored. Keys not included in the request body SHALL remain unchanged. The endpoint SHALL return the full settings object (in the new metadata format) after the update.

#### Scenario: Update editable setting
- **WHEN** an admin sends `PUT /api/settings` with `{"system_prompt": "New prompt"}`
- **THEN** the backend updates the setting and returns the full settings object with metadata

#### Scenario: Readonly setting ignored
- **WHEN** an admin sends `PUT /api/settings` with `{"openai_api_key": "sk-new"}` and the key is env-sourced
- **THEN** the write is silently ignored and the response shows the env-sourced value unchanged

#### Scenario: OIDC settings trigger hot-reload
- **WHEN** an admin sends `PUT /api/settings` with `{"oidc_discovery_url": "...", "oidc_client_id": "...", "oidc_client_secret": "..."}`
- **THEN** the backend saves the settings, performs OIDC discovery, and updates the auth mode

### Requirement: Settings endpoints exempt from general role check
The `/api/settings` endpoints SHALL use the `require_admin` dependency instead of the general `get_current_user` dependency. The `require_admin` dependency SHALL still validate the JWT and require authentication, but SHALL allow users with the `admin` role even if they have no other roles.

#### Scenario: Admin-only user accesses settings
- **WHEN** a user with only the `admin` role (and no other roles) requests `GET /api/settings`
- **THEN** the request succeeds with HTTP 200

### Requirement: LLM model list proxy endpoint
The backend SHALL expose `GET /api/llm/models` requiring the `admin` role. The endpoint SHALL resolve the LLM client using the settings registry (env var → DB → unconfigured). If the LLM provider is not configured via either source, the endpoint SHALL return HTTP 503.

#### Scenario: Models retrieved with env-sourced config
- **WHEN** `OPENAI_BASE_URL` and `OPENAI_API_KEY` are set via env vars
- **THEN** the endpoint uses those values and returns the model list

#### Scenario: Models retrieved with DB-sourced config
- **WHEN** LLM env vars are not set but `openai_base_url` and `openai_api_key` exist in the DB
- **THEN** the endpoint uses the DB values and returns the model list

#### Scenario: LLM not configured
- **WHEN** neither env vars nor DB settings provide LLM config
- **THEN** the endpoint returns HTTP 503 with `{"detail": "LLM provider not configured"}`

### Requirement: Regenerate MCP API key endpoint

The backend SHALL expose `POST /api/settings/regenerate-mcp-key` requiring the `admin` role. The endpoint SHALL generate a new 64-character hex API key via `secrets.token_hex(32)`, store it in the `settings` table with key `mcp_api_key` (overwriting any existing value), and return the new key in the response as `{"mcp_api_key": "<new-key>"}`.

#### Scenario: Regenerate API key

- **WHEN** an admin sends `POST /api/settings/regenerate-mcp-key`
- **THEN** a new API key is generated, stored in the settings table, and returned as `{"mcp_api_key": "<new-key>"}`

#### Scenario: Old key invalidated after regeneration

- **WHEN** an admin regenerates the API key and a client uses the old key for MCP requests
- **THEN** the MCP server rejects the request with an authentication error

#### Scenario: Non-admin user rejected

- **WHEN** a non-admin user sends `POST /api/settings/regenerate-mcp-key`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

### Requirement: Regenerate SSH keypair endpoint

The backend SHALL expose `POST /api/settings/regenerate-ssh-key` requiring the `admin` role. The endpoint SHALL generate a new Ed25519 SSH keypair, replace both `ssh_private_key` and `ssh_public_key` in the settings table, and return the new public key as `{"ssh_public_key": "<new-public-key>"}`.

#### Scenario: Regenerate SSH keypair

- **WHEN** an admin sends `POST /api/settings/regenerate-ssh-key`
- **THEN** a new Ed25519 keypair is generated, both keys are updated in the settings table, and the response contains `{"ssh_public_key": "<new-public-key>"}`

#### Scenario: Non-admin user rejected

- **WHEN** a non-admin user sends `POST /api/settings/regenerate-ssh-key`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

### Requirement: Cloud status event type
The existing task events WebSocket channel SHALL support a new `cloud_status` event type for real-time cloud connection state updates.

#### Scenario: Cloud status event published
- **WHEN** the cloud WebSocket client connects, disconnects, or encounters an error
- **THEN** a `cloud_status` event SHALL be published to the `task_events` Valkey channel
- **THEN** the event SHALL have the format: `{"event": "cloud_status", "status": "<connected|disconnected|error>", "detail": "<optional>"}`
- **THEN** all connected frontend WebSocket clients SHALL receive the event
