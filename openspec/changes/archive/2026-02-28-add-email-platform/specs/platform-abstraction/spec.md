## MODIFIED Requirements

### Requirement: PlatformCapability enum

The system SHALL define a `PlatformCapability` string enum with values: `POST`, `MEDIA`, `COMMANDS`, `WEBHOOKS`, `ANALYTICS`, `MONITORING`, `TOOL_PROVIDER`, `SEARCH`, `EMAIL`. Platforms declare their supported capabilities as a `set[PlatformCapability]`.

#### Scenario: Platform declares capabilities

- **WHEN** a `TwitterPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.POST` and `PlatformCapability.MEDIA`

#### Scenario: Email capability available

- **WHEN** an `EmailPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.EMAIL`

### Requirement: Platform registry initialization

The backend SHALL initialize a global `PlatformRegistry` during application startup (in the lifespan context manager) and register all built-in platforms. The registry SHALL be accessible via a module-level function `get_registry() -> PlatformRegistry`.

#### Scenario: Registry available after startup

- **WHEN** the FastAPI application has started
- **THEN** `get_registry()` returns a registry with `TwitterPlatform`, `SearXNGPlatform`, and `EmailPlatform` registered
