## ADDED Requirements

### Requirement: Qualified versioned adapter registry
The system SHALL expose only administrator-controlled adapter identities and validated schemas. A release SHALL pin adapter/vendor versions, protocol schema, per-architecture image digest/checksum and qualified runtime/auth tuples. Feature states SHALL distinguish supported, unsupported, unknown and experimental. Documented upstream capability SHALL NOT by itself qualify Errand support. Research-only adapters SHALL NOT be enabled automatically.

#### Scenario: Unsupported version or architecture
- **WHEN** a launch requests a vendor version, protocol schema or runtime architecture outside the qualified manifest
- **THEN** preparation fails before executing the harness

#### Scenario: Required and optional capability gaps
- **WHEN** a profile requires an unsupported or unknown capability
- **THEN** negotiation fails; optional missing telemetry instead produces a warning and unavailable values

#### Scenario: New adapter registration
- **WHEN** an administrator adds a real external harness
- **THEN** it remains unavailable until its schema, auth/legal policy, isolation, protocol and conformance evidence are approved

### Requirement: Authenticated deployment capability discovery
The system SHALL provide authenticated `GET /api/harnesses` discovery of deployment-qualified entries, capability states, approved releases, auth requirements and availability reasons without secrets. Existing unavailable profile intent SHALL remain readable; new unavailable selections SHALL be rejected while unrelated edits to already unavailable profiles remain possible.

#### Scenario: Runtime lacks an external adapter
- **WHEN** a client requests the harness catalog on an unqualified runtime
- **THEN** the catalog discloses the disabled entry and reason without claiming support or revealing credentials

#### Scenario: Rollback preserves selection
- **WHEN** an administrator disables an external release
- **THEN** profiles retain selection with an unavailable reason and new launches fail visibly rather than silently coercing builtin
