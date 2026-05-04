## Purpose

Backend settings definition registry with environment variable mapping, sensitivity flags, and resolution order.

## Requirements

### Requirement: Settings definition registry
The backend SHALL maintain a registry of all known settings. Each entry SHALL define: the setting key, the corresponding environment variable name (if applicable), whether the value is sensitive, and a default value (if any). The registry SHALL be defined as a Python data structure in a dedicated module.

The registry SHALL include a `telemetry_enabled` entry with: env var `TELEMETRY_ENABLED`, `sensitive: false`, default value `true`.

#### Scenario: Setting with env var mapping
- **WHEN** the registry defines `openai_api_key` with env var `OPENAI_API_KEY` and `sensitive: true`
- **THEN** the setting resolution uses the env var as the primary source and masks the value in API responses

#### Scenario: Setting with no env var
- **WHEN** the registry defines `system_prompt` with no env var mapping
- **THEN** the setting is always resolved from the database

#### Scenario: Telemetry setting registered
- **WHEN** the settings registry is loaded
- **THEN** it SHALL contain a `telemetry_enabled` entry with env var `TELEMETRY_ENABLED`, `sensitive: false`, and default value `true`

### Requirement: Setting resolution order
For each setting, the backend SHALL resolve the value in this order: (1) environment variable (if mapped and set), (2) database value, (3) default value from registry, (4) not configured. Settings sourced from env vars SHALL be marked `readonly: true`.

#### Scenario: Env var takes precedence over DB
- **WHEN** `OPENAI_API_KEY` env var is set to `sk-env` and the DB has `openai_api_key` = `sk-db`
- **THEN** the resolved value is `sk-env` with `source: "env"` and `readonly: true`

#### Scenario: DB value used when no env var
- **WHEN** `OPENAI_API_KEY` env var is not set and the DB has `openai_api_key` = `sk-db`
- **THEN** the resolved value is `sk-db` with `source: "database"` and `readonly: false`

#### Scenario: Default used when neither env nor DB
- **WHEN** `OPENAI_BASE_URL` env var is not set and no DB value exists, and the default is empty
- **THEN** the resolved value is empty with `source: "default"` and `readonly: false`

### Requirement: Sensitive value masking
When a setting is marked as sensitive and its source is `"env"`, the API response SHALL mask the value (show first 4 characters followed by `****`). Sensitive settings sourced from the database SHALL be returned in full (the admin entered them and needs to see them).

#### Scenario: Env-sourced sensitive value masked
- **WHEN** `OPENAI_API_KEY` is set via env var to `sk-proj-abc123def456`
- **THEN** the API returns `"value": "sk-p****"`

#### Scenario: DB-sourced sensitive value shown in full
- **WHEN** `openai_api_key` is stored in the DB as `sk-proj-abc123def456`
- **THEN** the API returns the full value

### Requirement: PUT /api/settings rejects readonly settings
When a `PUT /api/settings` request includes a key whose value is sourced from an environment variable (readonly), the backend SHALL ignore that key and not write it to the database. The response SHALL still reflect the env-sourced value.

#### Scenario: Attempt to override env-sourced setting
- **WHEN** an admin sends `PUT /api/settings` with `{"openai_api_key": "sk-new"}` and the key is env-sourced
- **THEN** the write is silently ignored and the response shows the env-sourced value unchanged

### Requirement: litellm_mcp_servers setting
The settings registry SHALL include a `litellm_mcp_servers` entry with no environment variable mapping, `sensitive: false`, and a default value of an empty list `[]`. The value SHALL be a JSON array of server alias strings.

#### Scenario: Default value
- **WHEN** no database entry exists for `litellm_mcp_servers` and no env var is mapped
- **THEN** the resolved value is `[]` with `source: "default"`

#### Scenario: Database value
- **WHEN** the database contains `litellm_mcp_servers` = `["argocd", "perplexity"]`
- **THEN** the resolved value is `["argocd", "perplexity"]` with `source: "database"`

### Requirement: Per-key resolver applies env → DB → default

The `settings_registry` module SHALL expose a coroutine that resolves a single registered setting key using the order **environment variable → database row → registered default**, returning a `(value, source)` tuple where `source` is one of `"env"`, `"database"`, or `"default"`.

The resolver SHALL coerce the resolved string into the type of the registered default (int, str, JSON-decoded dict/list). When the registered default is `None`, the resolver SHALL return the raw value as-is.

When coercion fails (e.g. malformed DB string), the resolver SHALL log at warning level and SHALL return `(default, "default")` rather than raising.

The resolver SHALL accept an optional pre-fetched mapping of DB rows so callers that batch-read multiple keys can avoid one DB round-trip per key.

#### Scenario: Env value takes precedence over DB row

- **WHEN** the registry has `max_concurrent_tasks` with `env_var=MAX_CONCURRENT_TASKS`, the env var is set to `7`, and the DB row's value is `4`
- **THEN** the resolver returns `(7, "env")`

#### Scenario: DB row used when no env value

- **WHEN** the env var for a registered key is unset (or empty) and the DB row exists with value `"4"`
- **THEN** the resolver returns `(4, "database")` with the integer coercion applied

#### Scenario: Default used when env and DB both absent

- **WHEN** neither the env var nor the DB row is set for a registered integer key with default `3`
- **THEN** the resolver returns `(3, "default")`

#### Scenario: Empty env string is treated as unset

- **WHEN** the env var is set to the empty string and a DB row exists
- **THEN** the resolver returns the DB-sourced value, not the empty string

#### Scenario: Coercion failure falls back to default

- **WHEN** the DB row contains a value that cannot be coerced to the default's type (e.g. `"abc"` for an int default of `3`)
- **THEN** the resolver logs at warning level and returns `(3, "default")`

#### Scenario: Pre-fetched DB rows are honoured

- **WHEN** the caller passes a `db_rows` mapping containing the key
- **THEN** the resolver uses that value instead of executing a `SELECT` against the session

### Requirement: `resolve_settings` delegates to the per-key resolver

`settings_registry.resolve_settings` SHALL build its returned dictionary by calling the per-key resolver (above) for every non-excluded key in the registry, preserving its existing behaviour: masking sensitive values only for env-sourced entries (per the "Sensitive value masking" requirement above — DB-sourced sensitive values are returned in full), populating `source`, `sensitive`, and `readonly` (true when `source == "env"`), and excluding keys listed in `EXCLUDED_KEYS`.

The shape of the returned dictionary, including key set and field names, SHALL NOT change.

#### Scenario: API response shape is preserved

- **WHEN** a client calls `GET /api/settings` after this refactor
- **THEN** the response payload has the same keys and same field names (`value`, `source`, `sensitive`, `readonly`) as before, and env-sourced values are still masked according to the existing rules
