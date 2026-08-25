## ADDED Requirements

### Requirement: A model's context window is resolvable

The system SHALL be able to determine the context window of the model serving a task, rather than assuming a single value for every model.

Resolution SHALL prefer the cheapest source that answers. `errand/model_metadata.py` already downloads `model_prices_and_context_window.json` and reads only two fields from it; where that file carries window data for a model, it SHALL be used. Where it does not, resolution MAY fall back to querying LiteLLM `/model/info` for the provider `api_base` and reading the provider's reported maximum context length.

Resolution SHALL degrade rather than fail. When no source answers for a model, the configured `max_context_tokens` SHALL apply unchanged, so an unresolvable model behaves exactly as today.

A resolved window SHALL NOT silently become the ceiling. The ceiling is a policy decision about how much of a window to use, and the relationship between resolved window and applied ceiling SHALL be explicit.

#### Scenario: Window resolved from existing metadata

- **WHEN** the model serving a task appears in `model_prices_and_context_window.json` with context window data
- **THEN** the window is resolved from that file
- **THEN** no additional network call is made

#### Scenario: Window resolved from the provider

- **WHEN** the model is absent from the metadata file and the provider reports a maximum context length
- **THEN** the window is resolved from the provider

#### Scenario: Unresolvable model falls back to the configured ceiling

- **WHEN** no source reports a context window for the model
- **THEN** the configured `max_context_tokens` applies unchanged
- **THEN** the task runs rather than failing

#### Scenario: Resolution is observable

- **WHEN** a window is resolved for a task
- **THEN** the resolved value and its source are recorded, so a ceiling that changed because resolution changed is explicable after the fact
