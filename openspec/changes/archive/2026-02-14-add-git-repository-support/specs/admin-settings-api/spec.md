## MODIFIED Requirements

### Requirement: Get all settings

The backend SHALL expose `GET /api/settings` requiring the `admin` role. The endpoint SHALL return a JSON object with all settings, where each key maps to its stored value. If no settings exist, the endpoint SHALL return an empty object `{}`. The `mcp_api_key` setting SHALL be included in the response when it exists. The `ssh_private_key` setting SHALL be excluded from the response — it SHALL never be returned by this endpoint.

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

#### Scenario: SSH public key included in settings response

- **WHEN** an admin requests `GET /api/settings` and `ssh_public_key` exists
- **THEN** the response includes the `ssh_public_key` value

#### Scenario: SSH private key excluded from settings response

- **WHEN** an admin requests `GET /api/settings` and `ssh_private_key` exists in the database
- **THEN** the response does NOT include the `ssh_private_key` key

## ADDED Requirements

### Requirement: Regenerate SSH keypair endpoint

The backend SHALL expose `POST /api/settings/regenerate-ssh-key` requiring the `admin` role. The endpoint SHALL generate a new Ed25519 SSH keypair, replace both `ssh_private_key` and `ssh_public_key` in the settings table, and return the new public key as `{"ssh_public_key": "<new-public-key>"}`.

#### Scenario: Regenerate SSH keypair

- **WHEN** an admin sends `POST /api/settings/regenerate-ssh-key`
- **THEN** a new Ed25519 keypair is generated, both keys are updated in the settings table, and the response contains `{"ssh_public_key": "<new-public-key>"}`

#### Scenario: Non-admin user rejected

- **WHEN** a non-admin user sends `POST /api/settings/regenerate-ssh-key`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`
