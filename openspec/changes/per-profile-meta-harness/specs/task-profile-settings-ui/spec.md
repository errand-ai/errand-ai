## ADDED Requirements

### Requirement: Separate per-profile harness and model controls
The shared profile editor SHALL present harness selection separately from model/provider selection, persist through existing profile APIs and default omitted selection to builtin. It SHALL use authenticated deployment capability discovery, show runtime/version/auth availability and capability gaps, and SHALL NOT present research-only, ambiguous phi or model/provider entries as supported harnesses. Switching harness SHALL preserve inactive builtin model settings.

#### Scenario: Existing profile opens in upgraded editor
- **WHEN** a migrated builtin profile is opened
- **THEN** builtin is selected and existing model/provider values remain unchanged

#### Scenario: Save and reload a qualified external choice
- **WHEN** a user chooses a deployment-qualified external harness and reloads the profile
- **THEN** the persisted choice and supported binding remain visible independently of other profiles

#### Scenario: Unsupported persisted choice after rollout rollback
- **WHEN** a previously selected harness becomes unavailable
- **THEN** the editor shows its retained identity and reason, does not silently reset it and permits unrelated edits

#### Scenario: User selects model branding as a harness
- **WHEN** model/provider catalogs contain Microsoft Phi or DeepSeek models
- **THEN** those entries do not appear as external harnesses and ambiguous phi requires clarification

### Requirement: Capability and credential disclosure
The editor SHALL disclose lost/unavailable builtin telemetry/safety features, supported auth routes, quota/cost uncertainty and required credential references without collecting prohibited Claude.ai tokens. UI implementations SHALL be coordinated in ui-components and integrated/tested in Errand; local wrappers alone SHALL NOT claim the feature delivered.

#### Scenario: Claude auth configuration is shown
- **WHEN** a user configures phase-2 Claude Code
- **THEN** approved API/cloud credential provisioning is described, no third-party subscription-token input is offered and zero incremental cost is not promised

#### Scenario: External usage is incomplete
- **WHEN** task results/events omit cost or per-turn usage
- **THEN** the shared viewer shows unavailable values rather than zero cost or fabricated builtin diagnostics
