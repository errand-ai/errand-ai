## MODIFIED Requirements

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
