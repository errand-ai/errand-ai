## ADDED Requirements

### Requirement: LLM provider category classification
The telemetry module SHALL classify each configured LLM provider's base URL into a category without exposing the raw URL.

#### Scenario: OpenAI provider
- **WHEN** a provider's base URL contains `api.openai.com`
- **THEN** the provider category SHALL be `openai`

#### Scenario: Anthropic provider
- **WHEN** a provider's base URL contains `api.anthropic.com`
- **THEN** the provider category SHALL be `anthropic`

#### Scenario: Google Gemini provider
- **WHEN** a provider's base URL contains `generativelanguage.googleapis.com`
- **THEN** the provider category SHALL be `gemini`

#### Scenario: xAI provider
- **WHEN** a provider's base URL contains `api.x.ai`
- **THEN** the provider category SHALL be `xai`

#### Scenario: Ollama provider
- **WHEN** a provider's base URL matches localhost or 127.0.0.1 on port 11434
- **THEN** the provider category SHALL be `ollama`

#### Scenario: Unknown LiteLLM provider
- **WHEN** a provider's base URL does not match any well-known pattern and the provider_type is `litellm`
- **THEN** the provider category SHALL be `litellm-other`

#### Scenario: Unknown OpenAI-compatible provider
- **WHEN** a provider's base URL does not match any well-known pattern and the provider_type is `openai_compatible`
- **THEN** the provider category SHALL be `openai-compatible-other`

#### Scenario: Completely unknown provider
- **WHEN** a provider's base URL does not match any well-known pattern and the provider_type is neither `litellm` nor `openai_compatible`
- **THEN** the provider category SHALL be `other`

### Requirement: LLM provider list in telemetry
The telemetry module SHALL include a list of all configured providers with their type and category.

#### Scenario: Providers collected
- **WHEN** a telemetry report is being prepared
- **THEN** `llm.providers` SHALL be an array of objects, each containing `type` (the provider_type from the database) and `category` (the classified category)

#### Scenario: No providers configured
- **WHEN** no LLM providers are configured
- **THEN** `llm.providers` SHALL be an empty array

### Requirement: LLM model settings in telemetry
The telemetry module SHALL include the model configuration for each model setting.

#### Scenario: Model settings collected
- **WHEN** a telemetry report is being prepared
- **THEN** `llm.models` SHALL be an object keyed by setting name (`llm_model`, `task_processing_model`, `transcription_model`), with each value containing `category` (the provider's classified category) and `model` (the model name string)

#### Scenario: Model setting not configured
- **WHEN** a model setting has no model configured (the model value is empty or null), regardless of provider configuration
- **THEN** that setting key SHALL be omitted from `llm.models`

#### Scenario: Model name included verbatim
- **WHEN** a model setting is configured with a model name
- **THEN** the model name SHALL be included as-is (e.g., `gpt-4o`, `claude-sonnet-4-20250514`, `llama3.1`)
