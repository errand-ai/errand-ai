## MODIFIED Requirements

### Requirement: LLM title generation from task description
When a new task is created with an input longer than 5 words, the backend SHALL call the LLM to generate a short title (2-5 words), categorise the task as `immediate`, `scheduled`, or `repeating`, and extract timing information. The LLM call SHALL use the `chat.completions.create` method with the model from the `llm_model` setting (default: `claude-haiku-4-5-20251001`). The LLM client SHALL be initialised using the settings resolution order: `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables first, then `openai_base_url` and `openai_api_key` database settings. If neither source provides the values, the LLM client SHALL not be initialized (same as current behavior when env vars are missing).

All other aspects of title generation (system prompt, JSON response format, timeout, fallback behavior, timezone handling) SHALL remain unchanged.

#### Scenario: LLM client configured from env vars
- **WHEN** `OPENAI_BASE_URL` and `OPENAI_API_KEY` env vars are set
- **THEN** the LLM client uses those values (existing behavior)

#### Scenario: LLM client configured from DB settings
- **WHEN** `OPENAI_BASE_URL` env var is not set but `openai_base_url` and `openai_api_key` exist in the settings table
- **THEN** the LLM client uses the DB-sourced values

#### Scenario: LLM client not available
- **WHEN** neither env vars nor DB settings provide LLM configuration
- **THEN** the task uses the fallback title (first 5 words + "..."), category `immediate`, and gets a "Needs Info" tag
