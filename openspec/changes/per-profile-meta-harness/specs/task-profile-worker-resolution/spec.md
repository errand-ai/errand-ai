## ADDED Requirements

### Requirement: Resolve and snapshot the profile harness before launch
The worker SHALL retain existing profile/default/tag precedence and independently resolve the selected harness from the persisted profile. It SHALL negotiate required capabilities, version and runtime qualification before launch, and SHALL snapshot profile revision, adapter/vendor versions, image digest, model/provider binding, permission/catalog hashes and non-secret credential reference into the attempt. Profile edits SHALL NOT alter a running attempt.

#### Scenario: Builtin execution remains default
- **WHEN** a legacy task resolves a profile without external selection
- **THEN** the worker runs the existing builtin behavior with existing model/provider precedence

#### Scenario: Unavailable selected adapter
- **WHEN** a profile's persisted external harness is disabled, unknown to this worker or unqualified on this runtime
- **THEN** launch fails with an actionable availability reason and the worker does not substitute builtin

#### Scenario: Profile changes during execution
- **WHEN** an administrator changes selection or policy after launch
- **THEN** the active attempt retains its immutable snapshot and subsequent attempts resolve the new configuration

### Requirement: Mixed-worker and concurrency safety
External attempts SHALL be claimed only by workers advertising the qualified registry release. Existing global concurrency limits SHALL apply with additional per-credential and profile limits. Each attempt and native session SHALL have an exclusive fenced execution lease and isolated state.

#### Scenario: Older worker cannot claim an external attempt
- **WHEN** a mixed deployment includes a builtin-only worker
- **THEN** that worker continues builtin work but cannot launch an external-selected attempt

#### Scenario: Two profiles share a provider account
- **WHEN** concurrent attempts reach the configured credential limit
- **THEN** further launches queue without exceeding the global or credential limit and without sharing native session state
