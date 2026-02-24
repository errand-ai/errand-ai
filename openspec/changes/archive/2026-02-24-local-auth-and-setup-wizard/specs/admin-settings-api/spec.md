## MODIFIED Requirements

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
