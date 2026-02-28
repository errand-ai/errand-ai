## MODIFIED Requirements

### Requirement: PlatformCapability enum

The system SHALL define a `PlatformCapability` string enum with values: `POST`, `MEDIA`, `COMMANDS`, `WEBHOOKS`, `ANALYTICS`, `MONITORING`, `EMAIL`, `SEARCH`. Platforms declare their supported capabilities as a `set[PlatformCapability]`.

#### Scenario: Platform declares capabilities

- **WHEN** a `TwitterPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.POST` and `PlatformCapability.MEDIA`

#### Scenario: Search capability available

- **WHEN** a `SearXNGPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.SEARCH`

### Requirement: Platform base class

The system SHALL provide a `Platform` abstract base class in `backend/platforms/base.py` that defines the common interface for all platforms. The class SHALL declare abstract methods `info()` returning `PlatformInfo` and `verify_credentials(credentials: dict)` returning `bool`. The class SHALL provide default implementations for optional methods (`post()`, `delete_post()`, `get_post()`, `search()`) that raise `NotImplementedError`.

#### Scenario: Platform subclass must implement info

- **WHEN** a class inherits from `Platform` without implementing `info()`
- **THEN** instantiation raises `TypeError` indicating the abstract method is not implemented

#### Scenario: Platform subclass must implement verify_credentials

- **WHEN** a class inherits from `Platform` without implementing `verify_credentials()`
- **THEN** instantiation raises `TypeError` indicating the abstract method is not implemented

#### Scenario: Optional methods raise NotImplementedError by default

- **WHEN** a platform that does not override `post()` has `post()` called
- **THEN** a `NotImplementedError` is raised

#### Scenario: Search method raises NotImplementedError by default

- **WHEN** a platform that does not override `search()` has `search()` called
- **THEN** a `NotImplementedError` is raised

### Requirement: Platform registry initialization

The backend SHALL initialize a global `PlatformRegistry` during application startup (in the lifespan context manager) and register all built-in platforms. The registry SHALL be accessible via a module-level function `get_registry() -> PlatformRegistry`.

#### Scenario: Registry available after startup

- **WHEN** the FastAPI application has started
- **THEN** `get_registry()` returns a registry with `TwitterPlatform` and `SearXNGPlatform` registered
