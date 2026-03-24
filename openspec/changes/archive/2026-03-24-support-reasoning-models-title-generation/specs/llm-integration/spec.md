## MODIFIED Requirements

### Requirement: LLM title generation from task description
When a new task is created with an input longer than 5 words, the backend SHALL call the LLM to generate a short title (2-5 words), categorise the task as `immediate`, `scheduled`, or `repeating`, extract timing information, and produce a cleaned task description with scheduling/timing references removed. The LLM call SHALL use the `chat.completions.create` method with the model and provider from the `llm_model` setting (stored as `{"provider_id": "<uuid>", "model": "<model-id>"}`). If the setting is empty or the provider no longer exists, the fallback title SHALL be used. The system SHALL resolve the provider ID to an `AsyncOpenAI` client via the client pool (`get_client_for_provider`). The system prompt SHALL instruct the model to return a JSON object with fields: `title` (string, 2-5 words), `category` (immediate|scheduled|repeating), `execute_at` (ISO 8601 datetime string or null), `repeat_interval` (string like "15m", "1h", "1d", or crontab expression, or null), `repeat_until` (ISO 8601 datetime string or null), `description` (string: the task description with all scheduling and timing references removed, containing only what needs to be done). The call SHALL use a timeout read from the `llm_timeout` setting (in seconds). If no `llm_timeout` setting exists, the timeout SHALL default to `30` seconds.

The system prompt SHALL include the current UTC datetime and the user's configured timezone so the LLM can resolve relative time references (e.g. "in 10 minutes", "at 5pm", "tomorrow morning", "end of the working day") to concrete ISO 8601 timestamps. The datetime SHALL be formatted as ISO 8601 (e.g. `2026-02-11T14:30:00Z`) and the timezone SHALL be an IANA timezone name (e.g. `Europe/London`). If no timezone setting is configured, the prompt SHALL default to `UTC`.

The `generate_title` function SHALL accept an optional `now` parameter (`datetime | None`, default `None`). When `None`, the function SHALL use `datetime.now(timezone.utc)`. This allows tests to inject a known datetime without mocking.

The LLM client SHALL be resolved from the `llm_model` setting's `provider_id` via the provider table and client pool, replacing the previous `OPENAI_BASE_URL`/`OPENAI_API_KEY` env var pattern.

The `LLMResult` dataclass SHALL include a `description` field (`str | None`, default `None`) to carry the cleaned description returned by the LLM.

The `_parse_llm_response` function SHALL extract the `description` field from the LLM JSON response. If the field is missing or not a string, `description` SHALL be `None`.

**The `max_tokens` parameter for the LLM call SHALL be determined dynamically.** Before making the call, the function SHALL look up the configured model name in the model metadata cache (via the lookup function from the `model-metadata-registry` capability). If a `max_output_tokens` value is found, it SHALL be used as the `max_tokens` parameter. If no match is found in the cache, the function SHALL use the default value of `300`.

**After receiving the LLM response, the function SHALL check for reasoning model responses.** If `response.choices[0].message.content` is empty (or whitespace-only) and the response message has a non-empty `reasoning_content` attribute, the function SHALL log a warning: "Model '{model}' returned reasoning_content but empty content — model may not be suitable for structured output tasks. Consider using a non-reasoning model for title generation." The function SHALL then proceed with the existing fallback behavior (fallback title, `success=False`).

#### Scenario: Successful title generation with provider-scoped model
- **WHEN** a task is created with a long input and `llm_model` is `{"provider_id": "uuid-1", "model": "claude-haiku-4-5-20251001"}`
- **THEN** the backend resolves provider "uuid-1" from the provider table, creates/reuses a client, and calls `chat.completions.create` with model "claude-haiku-4-5-20251001"

#### Scenario: Model setting empty after provider deletion
- **WHEN** a task is created and `llm_model` is `{"provider_id": null, "model": ""}`
- **THEN** the fallback title is used (first 5 words + "...")

#### Scenario: Provider no longer exists
- **WHEN** a task is created and `llm_model` references a provider_id that is not in the provider table
- **THEN** the fallback title is used and the error is logged

#### Scenario: Scheduled task categorisation
- **WHEN** a task is created with input "Send the quarterly financial report to the board at 5pm today"
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `scheduled`, execute_at set to 5pm today (UTC-adjusted for the configured timezone), repeat_interval null, and description "Send the quarterly financial report to the board"

#### Scenario: Scheduled task description cleaned of timing references
- **WHEN** a task is created with input "In two hours, publish one of the approved tweets"
- **THEN** the LLM returns a JSON response with category `scheduled`, execute_at set to 2 hours from now, and description "Publish one of the approved tweets" (timing reference removed)

#### Scenario: Repeating task description cleaned of timing references
- **WHEN** a task is created with input "Every Monday at 9am, check the sales dashboard"
- **THEN** the LLM returns a JSON response with category `repeating`, repeat_interval set appropriately, and description "Check the sales dashboard" (timing reference removed)

#### Scenario: Immediate task description unchanged
- **WHEN** a task is created with input "Fix the login bug on the settings page"
- **THEN** the LLM returns a JSON response with category `immediate` and description "Fix the login bug on the settings page" (no timing to remove)

#### Scenario: LLM call fails
- **WHEN** a task is created with a long input and the LLM call fails or times out
- **THEN** the task is created with the first 5 words of the input plus "..." as the title, category `immediate`, execute_at set to current server time, repeat_interval null, repeat_until null, description set to the raw input, and a "Needs Info" tag is applied

#### Scenario: Custom timeout from settings
- **WHEN** `generate_title` is called and the `llm_timeout` setting is `60`
- **THEN** the LLM chat completion call uses a 60-second timeout

#### Scenario: Default timeout when not configured
- **WHEN** `generate_title` is called and no `llm_timeout` setting exists in the database
- **THEN** the LLM chat completion call uses the default 30-second timeout

#### Scenario: Dynamic max_tokens from metadata cache
- **WHEN** `generate_title` is called with model `deepseek-r1:8b` and the metadata cache has `max_output_tokens=8192` for `deepseek-r1`
- **THEN** the LLM call uses `max_tokens=8192`

#### Scenario: Default max_tokens when model not in cache
- **WHEN** `generate_title` is called with model `custom-finetune:7b` and the metadata cache has no match
- **THEN** the LLM call uses the default `max_tokens=300`

#### Scenario: Reasoning model returns empty content with reasoning_content
- **WHEN** `generate_title` is called with a reasoning model and the response has empty `content` but non-empty `reasoning_content`
- **THEN** a warning is logged identifying the model as a reasoning model that may not be suitable for structured output
- **THEN** the fallback title is used with `success=False`

#### Scenario: Non-reasoning model returns empty content without reasoning_content
- **WHEN** `generate_title` is called and the response has empty `content` and no `reasoning_content`
- **THEN** the fallback title is used with `success=False` (existing behavior, no additional warning)
