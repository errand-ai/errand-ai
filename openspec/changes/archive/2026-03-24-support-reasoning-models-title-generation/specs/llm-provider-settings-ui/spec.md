## MODIFIED Requirements

### Requirement: Provider dropdown on model selectors
Each model selector (Title Generation, Task Processing, Transcription) in the "LLM Models" section SHALL display a provider dropdown to the left of the model selector. The provider dropdown SHALL list all configured providers by name. When a provider is selected, the model dropdown SHALL fetch models from `GET /api/llm/providers/{id}/models` (with `?mode=audio_transcription` for the transcription selector on LiteLLM providers). The model list endpoint SHALL return an array of objects with fields: `id` (string, the model name), `supports_reasoning` (boolean or null), `max_output_tokens` (integer or null). For `unknown` providers, the model selector SHALL render as a free-text input instead of a dropdown. Saving a model setting SHALL persist `{provider_id, model}`.

When a model with `supports_reasoning: true` is selected for the Title Generation or Task Processing model role, the UI SHALL display an inline warning below the model selector: "This is a reasoning model. It may be slower and less reliable for structured output tasks like title generation. Consider using a non-reasoning model." The warning SHALL be styled as a cautionary notice (amber/yellow). No warning SHALL be shown for models with `supports_reasoning: false` or `supports_reasoning: null`.

#### Scenario: Select provider then model
- **WHEN** an admin selects "OpenAI" from the provider dropdown for Title Generation
- **THEN** the model dropdown fetches and displays models from the OpenAI provider

#### Scenario: Unknown provider shows free-text input
- **WHEN** an admin selects a provider with type `unknown` for any model role
- **THEN** the model selector renders as a text input instead of a dropdown

#### Scenario: Cleared model setting shows empty state
- **WHEN** a model setting has been cleared (provider was deleted)
- **THEN** both provider and model selectors show placeholder text prompting the user to select

#### Scenario: Transcription model dropdown for LiteLLM
- **WHEN** an admin selects a LiteLLM provider for the transcription model
- **THEN** the model dropdown fetches models with `?mode=audio_transcription`

#### Scenario: Transcription model dropdown for non-LiteLLM
- **WHEN** an admin selects an OpenAI-compatible provider for the transcription model
- **THEN** the model dropdown shows all models (unfiltered)

#### Scenario: Reasoning model warning shown for title generation
- **WHEN** an admin selects a model with `supports_reasoning: true` for the Title Generation role
- **THEN** an amber inline warning is displayed below the model selector advising that reasoning models may be slower and less reliable for structured output

#### Scenario: No warning for non-reasoning model
- **WHEN** an admin selects a model with `supports_reasoning: false` for Title Generation
- **THEN** no warning is displayed

#### Scenario: No warning for unknown model
- **WHEN** an admin selects a model with `supports_reasoning: null` (not in metadata cache) for Title Generation
- **THEN** no warning is displayed

#### Scenario: Model list returns enriched objects
- **WHEN** the model dropdown fetches models from `GET /api/llm/providers/{id}/models`
- **THEN** each item in the response is an object with `id`, `supports_reasoning`, and `max_output_tokens` fields
