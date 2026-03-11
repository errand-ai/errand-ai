## ADDED Requirements

### Requirement: PostgreSQL version collection
The telemetry module SHALL collect the PostgreSQL server version at report time.

#### Scenario: PostgreSQL version retrieved
- **WHEN** a telemetry report is being prepared
- **THEN** the module SHALL execute `SELECT version()` via the existing async database session and extract the version number (e.g., `16.2`)
- **AND** `infrastructure.postgres_version` SHALL be set to the extracted version string

#### Scenario: PostgreSQL version query fails
- **WHEN** the `SELECT version()` query fails
- **THEN** `infrastructure.postgres_version` SHALL be `null`
- **AND** the failure SHALL be logged at warning level

### Requirement: Valkey version and connectivity collection
The telemetry module SHALL collect the Valkey server version and connectivity status at report time.

#### Scenario: Valkey connected and version available
- **WHEN** a Valkey connection is available via `get_valkey()` and the `INFO server` command succeeds
- **THEN** `infrastructure.valkey_version` SHALL be set to the `redis_version` field from the INFO response
- **AND** `infrastructure.valkey_connected` SHALL be `true`

#### Scenario: Valkey connected but INFO restricted
- **WHEN** a Valkey connection is available but the `INFO server` command raises an error
- **THEN** `infrastructure.valkey_version` SHALL be `null`
- **AND** `infrastructure.valkey_connected` SHALL be `true`

#### Scenario: Valkey not configured or unavailable
- **WHEN** `get_valkey()` returns `None`
- **THEN** `infrastructure.valkey_version` SHALL be `null`
- **AND** `infrastructure.valkey_connected` SHALL be `false`
