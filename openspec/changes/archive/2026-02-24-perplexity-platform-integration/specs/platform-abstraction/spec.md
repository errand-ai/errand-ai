## MODIFIED Requirements

### Requirement: PlatformCapability enum
The system SHALL define a `PlatformCapability` string enum with values: `POST`, `MEDIA`, `COMMANDS`, `WEBHOOKS`, `ANALYTICS`, `MONITORING`, `TOOL_PROVIDER`. Platforms declare their supported capabilities as a `set[PlatformCapability]`.

#### Scenario: Platform declares capabilities
- **WHEN** a `TwitterPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.POST` and `PlatformCapability.MEDIA`

#### Scenario: Tool provider declares capability
- **WHEN** a `PerplexityPlatform` is instantiated
- **THEN** its `info().capabilities` includes `PlatformCapability.TOOL_PROVIDER`
