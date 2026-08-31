## MODIFIED Requirements

### Requirement: Update settings
The backend SHALL expose `PUT /api/settings` requiring the `admin` role. The endpoint SHALL accept a JSON object where each key-value pair is upserted into the settings table. Keys whose values are sourced from environment variables (readonly) SHALL NOT be persisted; the endpoint SHALL log a WARNING naming the setting key and the environment variable that shadows it, and SHALL still return HTTP 200 so that editable keys sent in the same request are saved. Keys not included in the request body SHALL remain unchanged. The endpoint SHALL return the full settings object (in the metadata format), in which every refused key carries `source: "env"` and `readonly: true` — the signal a client diffs against the keys it sent to determine which writes were refused.

#### Scenario: Update editable setting
- **WHEN** an admin sends `PUT /api/settings` with `{"system_prompt": "New prompt"}`
- **THEN** the backend updates the setting and returns the full settings object with metadata

#### Scenario: Readonly setting ignored
- **WHEN** an admin sends `PUT /api/settings` with `{"openai_api_key": "sk-new"}` and the key is env-sourced
- **THEN** the value SHALL NOT be written to the settings table
- **AND** the backend SHALL log a WARNING naming the key and its environment variable
- **AND** the response SHALL show the env-sourced value unchanged with `source: "env"` and `readonly: true`

#### Scenario: Editable key saved alongside a refused key
- **WHEN** an admin sends `PUT /api/settings` with both an editable key and an env-shadowed key in one request
- **THEN** the request SHALL succeed with HTTP 200
- **AND** the editable key SHALL be persisted
- **AND** the env-shadowed key SHALL be refused as above

#### Scenario: OIDC settings trigger hot-reload
- **WHEN** an admin sends `PUT /api/settings` with `{"oidc_discovery_url": "...", "oidc_client_id": "...", "oidc_client_secret": "..."}`
- **THEN** the backend saves the settings, performs OIDC discovery, and updates the auth mode
