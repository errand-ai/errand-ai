## ADDED Requirements

### Requirement: Model mode is resolved from the metadata registry

The model metadata registry SHALL extract and expose each model's mode — whether it is a chat model, an embedding model, or another kind — alongside the capabilities it already resolves. Mode SHALL be looked up using the same normalisation already applied to model names, including the alternate normalisation that reconciles local runtime naming with registry naming.

#### Scenario: Chat model classified

- **WHEN** metadata is resolved for a model the registry records as a chat model
- **THEN** the resolved metadata reports it as a chat model

#### Scenario: Embedding model classified

- **WHEN** metadata is resolved for a model the registry records as an embedding model
- **THEN** the resolved metadata reports it as an embedding model

#### Scenario: Local runtime naming reconciled

- **WHEN** a model name uses a local runtime's naming convention that differs from the registry's by digit separation
- **THEN** the alternate normalisation is applied and the registry entry is found

#### Scenario: Unknown model

- **WHEN** metadata is resolved for a model absent from the registry
- **THEN** the mode is reported as unknown
- **AND** no error is raised

### Requirement: Provider-reported mode takes precedence over the registry

When a provider reports a model's mode itself, that value SHALL be used in preference to the registry lookup. The registry SHALL be consulted only for models whose provider does not report a mode.

#### Scenario: Provider reports mode

- **WHEN** a provider's model listing reports a mode for a model
- **THEN** that mode is used

#### Scenario: Provider silent on mode

- **WHEN** a provider's model listing carries no mode information
- **THEN** the mode is resolved from the metadata registry

### Requirement: Model listing can be filtered by mode for any provider type

Filtering a provider's models by mode SHALL work for every provider type, not only for those whose listing endpoint reports mode natively. For providers that do not report mode, the filter SHALL be applied using resolved metadata.

#### Scenario: Filtering a provider that does not report mode

- **WHEN** models are listed with a mode filter for a provider whose listing carries no mode
- **THEN** the returned models are those whose resolved metadata matches the requested mode

#### Scenario: Unknown-mode models are not silently dropped

- **WHEN** a mode filter is applied and some models have unknown mode
- **THEN** those models are distinguishable from models positively identified as a different mode, so the caller can still select one
