## MODIFIED Requirements

### Requirement: Get all settings

The backend SHALL expose `GET /api/settings` requiring the `admin` role. The endpoint SHALL return a JSON object with all settings, where each key maps to its stored value. If no settings exist, the endpoint SHALL return an empty object `{}`. The `mcp_api_key` setting SHALL be included in the response when it exists.

#### Scenario: Settings exist

- **WHEN** an admin requests `GET /api/settings` and settings `system_prompt` and `mcp_servers` exist
- **THEN** the backend returns HTTP 200 with `{"system_prompt": "...", "mcp_servers": [...]}`

#### Scenario: No settings exist

- **WHEN** an admin requests `GET /api/settings` and the settings table is empty
- **THEN** the backend returns HTTP 200 with `{}`

#### Scenario: Non-admin user

- **WHEN** a non-admin user requests `GET /api/settings`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

#### Scenario: API key included in settings response

- **WHEN** an admin requests `GET /api/settings` and an `mcp_api_key` exists
- **THEN** the response includes the `mcp_api_key` value

## ADDED Requirements

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
