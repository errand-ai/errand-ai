## ADDED Requirements

### Requirement: Independent persisted harness selection
The system SHALL persist `harness_id` and non-secret schema-versioned `harness_config` per TaskProfile independently of model/provider fields. Existing rows and new profiles omitting selection SHALL resolve to `builtin`. A model/provider name, image or installed executable SHALL NOT implicitly select a harness. Unknown ids, ambiguous `phi`, null ids and malformed configuration SHALL be rejected with validation errors.

#### Scenario: Migration preserves legacy profiles
- **WHEN** existing profiles are migrated and a legacy client creates a profile without harness fields
- **THEN** both use `builtin` and retain existing model/provider/tool resolution

#### Scenario: Profiles choose different agent loops
- **WHEN** one profile persists builtin and another persists a deployment-qualified external harness
- **THEN** each retains its choice across restart and executes only its selected harness

#### Scenario: Provider is not a harness
- **WHEN** a profile selects a DeepSeek or Microsoft Phi model without changing harness_id
- **THEN** its harness remains unchanged and no external executable is inferred

### Requirement: Harness round-trip and secret-free configuration
Profile CRUD, clone and MCP profile operations SHALL preserve harness fields. Update omission SHALL preserve existing values. Export SHALL exclude secrets and export/import SHALL require credential references to be rebound in the authorized destination. Switching harness SHALL preserve inactive model fields without forwarding unsupported model aliases to an external adapter.

#### Scenario: Old client edits an external profile
- **WHEN** an old client updates unrelated profile fields without harness fields
- **THEN** the persisted external selection remains unchanged

#### Scenario: Invalid and unauthorized configuration
- **WHEN** configuration contains a raw secret, arbitrary executable/image override, unsupported binding or unauthorized credential reference
- **THEN** the write fails without saving that configuration

#### Scenario: Clone and import retain explicit intent
- **WHEN** an external profile is cloned or exported and imported
- **THEN** its harness intent is retained and credentials are not copied as secret values or authorized implicitly
