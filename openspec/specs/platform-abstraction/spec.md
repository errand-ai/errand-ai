## Purpose

Platform abstraction layer that defines a common interface for messaging platforms (Twitter, Slack, etc.), a capability model, and a registry for managing platform instances.

## Requirements

### Requirement: Platform base class
The system SHALL provide a `Platform` abstract base class in `backend/platforms/base.py` that defines the common interface for all messaging platforms. The class SHALL declare abstract methods `info()` returning `PlatformInfo` and `verify_credentials(credentials: dict)` returning `bool`. The class SHALL provide default implementations for optional methods (`post()`, `delete_post()`, `get_post()`) that raise `NotImplementedError`.

#### Scenario: Platform subclass must implement info
- **WHEN** a class inherits from `Platform` without implementing `info()`
- **THEN** instantiation raises `TypeError` indicating the abstract method is not implemented

#### Scenario: Platform subclass must implement verify_credentials
- **WHEN** a class inherits from `Platform` without implementing `verify_credentials()`
- **THEN** instantiation raises `TypeError` indicating the abstract method is not implemented

#### Scenario: Optional methods raise NotImplementedError by default
- **WHEN** a platform that does not override `post()` has `post()` called
- **THEN** a `NotImplementedError` is raised

### Requirement: PlatformCapability enum
The system SHALL define a `PlatformCapability` string enum with values: `POST`, `MEDIA`, `COMMANDS`, `WEBHOOKS`, `ANALYTICS`, `MONITORING`. Platforms declare their supported capabilities as a `set[PlatformCapability]`.

#### Scenario: Platform declares capabilities
- **WHEN** a `TwitterPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.POST` and `PlatformCapability.MEDIA`

### Requirement: PlatformInfo dataclass
The system SHALL define a `PlatformInfo` dataclass with fields: `id` (str), `label` (str), `capabilities` (set of PlatformCapability), and `credential_schema` (dict describing required credential fields with name, type, label, and optional help_text for each field).

#### Scenario: PlatformInfo contains credential schema
- **WHEN** `TwitterPlatform.info()` is called
- **THEN** the returned `PlatformInfo` includes a `credential_schema` with entries for `api_key`, `api_secret`, `access_token`, and `access_secret`

### Requirement: Platform registry
The system SHALL provide a `PlatformRegistry` class in `backend/platforms/__init__.py` that maintains a dict of registered `Platform` instances keyed by platform ID. The registry SHALL provide methods: `register(platform)`, `get(platform_id) -> Platform | None`, `list_all() -> list[PlatformInfo]`, and `list_configured() -> list[PlatformInfo]` (platforms that have verified credentials in the DB).

#### Scenario: Register and retrieve a platform
- **WHEN** a `TwitterPlatform` is registered and `registry.get("twitter")` is called
- **THEN** the `TwitterPlatform` instance is returned

#### Scenario: Get non-existent platform returns None
- **WHEN** `registry.get("nonexistent")` is called
- **THEN** `None` is returned

#### Scenario: List all platforms
- **WHEN** Twitter is registered and `registry.list_all()` is called
- **THEN** the result includes `PlatformInfo` for Twitter

#### Scenario: List configured platforms
- **WHEN** Twitter is registered with verified credentials and LinkedIn is registered without credentials
- **THEN** `registry.list_configured()` includes only Twitter

### Requirement: Platform registry initialization
The backend SHALL initialize a global `PlatformRegistry` during application startup (in the lifespan context manager) and register all built-in platforms. The registry SHALL be accessible via a module-level function `get_registry() -> PlatformRegistry`.

#### Scenario: Registry available after startup
- **WHEN** the FastAPI application has started
- **THEN** `get_registry()` returns a registry with `TwitterPlatform` registered

### Requirement: Platform list API endpoint
The backend SHALL expose `GET /api/platforms` requiring any authenticated user. The endpoint SHALL return a JSON array of platform info objects, each containing `id`, `label`, `capabilities` (as string list), `credential_schema`, and `is_configured` (bool).

#### Scenario: List platforms
- **WHEN** an authenticated user requests `GET /api/platforms`
- **THEN** the response includes platform entries with their configuration status

#### Scenario: Unauthenticated request
- **WHEN** an unauthenticated user requests `GET /api/platforms`
- **THEN** the backend returns HTTP 401
