## ADDED Requirements

### Requirement: Telemetry opt-out setting
The service SHALL provide a `telemetry_enabled` setting that allows users to disable telemetry collection and reporting.

#### Scenario: Default enabled
- **WHEN** no `telemetry_enabled` setting exists in the database and no `TELEMETRY_ENABLED` environment variable is set
- **THEN** telemetry SHALL be enabled (default `true`)

#### Scenario: Disabled via Settings UI
- **WHEN** the user sets `telemetry_enabled` to `false` via the Settings UI
- **THEN** telemetry collection and reporting SHALL stop

#### Scenario: Disabled via environment variable
- **WHEN** the `TELEMETRY_ENABLED` environment variable is set to `false`
- **THEN** telemetry SHALL be disabled and the Settings UI toggle SHALL be readonly

#### Scenario: Environment variable overrides database
- **WHEN** `TELEMETRY_ENABLED=false` is set and the database has `telemetry_enabled = true`
- **THEN** telemetry SHALL be disabled (env var takes precedence)

### Requirement: Telemetry toggle in Settings UI
The Settings UI SHALL include a toggle for the telemetry opt-out setting.

#### Scenario: Display telemetry toggle
- **WHEN** the user navigates to the Settings page
- **THEN** the Settings UI SHALL display a toggle labeled "Usage Telemetry" with a description explaining that anonymous usage data is sent to help improve Errand

#### Scenario: Readonly when env var set
- **WHEN** the `TELEMETRY_ENABLED` environment variable is set
- **THEN** the toggle SHALL be displayed as readonly with an indication that it is controlled by an environment variable
