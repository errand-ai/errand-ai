## MODIFIED Requirements

### Requirement: PlatformCapability enum

The system SHALL define a `PlatformCapability` string enum with values: `POST`, `MEDIA`, `COMMANDS`, `WEBHOOKS`, `ANALYTICS`, `MONITORING`, `EMAIL`, `SEARCH`. Platforms declare their supported capabilities as a `set[PlatformCapability]`.

#### Scenario: Platform declares capabilities

- **WHEN** a `TwitterPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.POST`, `PlatformCapability.MEDIA`, `PlatformCapability.ANALYTICS`, and `PlatformCapability.SEARCH`

#### Scenario: Email capability available

- **WHEN** an `EmailPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.EMAIL`

#### Scenario: Search capability available

- **WHEN** a `SearXNGPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.SEARCH`
