## MODIFIED Requirements

### Requirement: LLM title generation from task description
When a new task is created with an input longer than 5 words, the backend SHALL call the LLM to generate a short title (2-5 words), categorise the task as `immediate`, `scheduled`, or `repeating`, and extract timing information. The LLM call SHALL use the `chat.completions.create` method with the model and provider from the `llm_model` setting (stored as `{"provider_id": "<uuid>", "model": "<model-id>"}`). If the setting is empty or the provider no longer exists, the fallback title SHALL be used. The system SHALL resolve the provider ID to an `AsyncOpenAI` client via the client pool (`get_client_for_provider`). The system prompt SHALL instruct the model to return a JSON object with fields: `title` (string, 2-5 words), `category` (immediate|scheduled|repeating), `execute_at` (ISO 8601 datetime string or null), `repeat_interval` (string like "15m", "1h", "1d", or crontab expression, or null), `repeat_until` (ISO 8601 datetime string or null). The call SHALL use a timeout read from the `llm_timeout` setting (in seconds). If no `llm_timeout` setting exists, the timeout SHALL default to `30` seconds.

The system prompt SHALL include the current UTC datetime and the user's configured timezone so the LLM can resolve relative time references (e.g. "in 10 minutes", "at 5pm", "tomorrow morning", "end of the working day") to concrete ISO 8601 timestamps. The datetime SHALL be formatted as ISO 8601 (e.g. `2026-02-11T14:30:00Z`) and the timezone SHALL be an IANA timezone name (e.g. `Europe/London`). If no timezone setting is configured, the prompt SHALL default to `UTC`.

The `generate_title` function SHALL accept an optional `now` parameter (`datetime | None`, default `None`). When `None`, the function SHALL use `datetime.now(timezone.utc)`. This allows tests to inject a known datetime without mocking.

The LLM client SHALL be resolved from the `llm_model` setting's `provider_id` via the provider table and client pool, replacing the previous `OPENAI_BASE_URL`/`OPENAI_API_KEY` env var pattern.

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
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `scheduled`, execute_at set to 5pm today (UTC-adjusted for the configured timezone), and repeat_interval null

#### Scenario: LLM call fails
- **WHEN** a task is created with a long input and the LLM call fails or times out
- **THEN** the task is created with the first 5 words of the input plus "..." as the title, category `immediate`, execute_at set to current server time, repeat_interval null, repeat_until null, and a "Needs Info" tag is applied

#### Scenario: Custom timeout from settings
- **WHEN** `generate_title` is called and the `llm_timeout` setting is `60`
- **THEN** the LLM chat completion call uses a 60-second timeout

#### Scenario: Default timeout when not configured
- **WHEN** `generate_title` is called and no `llm_timeout` setting exists in the database
- **THEN** the LLM chat completion call uses the default 30-second timeout

## REMOVED Requirements

### Requirement: LLM client not available
**Reason**: The "LLM client not available" scenario (missing env vars) is replaced by provider-scoped client resolution. If no providers exist or the model setting is empty, the fallback title is used (covered by the modified scenarios above).
**Migration**: LLM availability is now determined by the existence of providers in the `llm_provider` table, not by `OPENAI_BASE_URL`/`OPENAI_API_KEY` env vars.
