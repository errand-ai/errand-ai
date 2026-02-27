## Purpose

LLM-powered task classification — title generation, category detection, timing extraction, and timezone-aware scheduling.

## Requirements

### Requirement: LLM title generation from task description
When a new task is created with an input longer than 5 words, the backend SHALL call the LLM to generate a short title (2-5 words), categorise the task as `immediate`, `scheduled`, or `repeating`, and extract timing information. The LLM call SHALL use the `chat.completions.create` method with the model from the `llm_model` setting (default: `claude-haiku-4-5-20251001`). The system prompt SHALL instruct the model to return a JSON object with fields: `title` (string, 2-5 words), `category` (immediate|scheduled|repeating), `execute_at` (ISO 8601 datetime string or null), `repeat_interval` (string like "15m", "1h", "1d", or crontab expression, or null), `repeat_until` (ISO 8601 datetime string or null). The call SHALL use a timeout read from the `llm_timeout` setting (in seconds). If no `llm_timeout` setting exists, the timeout SHALL default to `30` seconds.

The system prompt SHALL include the current UTC datetime and the user's configured timezone so the LLM can resolve relative time references (e.g. "in 10 minutes", "at 5pm", "tomorrow morning", "end of the working day") to concrete ISO 8601 timestamps. The datetime SHALL be formatted as ISO 8601 (e.g. `2026-02-11T14:30:00Z`) and the timezone SHALL be an IANA timezone name (e.g. `Europe/London`). If no timezone setting is configured, the prompt SHALL default to `UTC`.

The `generate_title` function SHALL accept an optional `now` parameter (`datetime | None`, default `None`). When `None`, the function SHALL use `datetime.now(timezone.utc)`. This allows tests to inject a known datetime without mocking.

The LLM client SHALL be initialised using `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables (replacing the previous `LITELLM_BASE_URL` and `LITELLM_API_KEY` names).

#### Scenario: Successful title and categorisation
- **WHEN** a task is created with input "The login page throws a 500 error when users with special characters try to reset their password"
- **THEN** the backend calls the LLM and receives a JSON response with title, category `immediate`, execute_at set to approximately now, and repeat_interval null

#### Scenario: Scheduled task categorisation
- **WHEN** a task is created with input "Send the quarterly financial report to the board at 5pm today"
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `scheduled`, execute_at set to 5pm today (UTC-adjusted for the configured timezone), and repeat_interval null

#### Scenario: Repeating task categorisation
- **WHEN** a task is created with input "Check the production server health dashboard every 30 minutes and report any anomalies"
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `repeating`, execute_at set to approximately now, repeat_interval `"30m"`, and repeat_until null

#### Scenario: Relative time reference resolved correctly
- **WHEN** a task is created with input "Remind me to check the deployment in 10 minutes" and the current UTC time is 2026-02-11T14:30:00Z
- **THEN** the LLM receives the current datetime in the system prompt and returns execute_at approximately `2026-02-11T14:40:00Z`, category `scheduled`

#### Scenario: End-of-day reference resolved with timezone
- **WHEN** a task is created with input "Send the daily summary at the end of the working day" and the timezone setting is `Europe/London`
- **THEN** the LLM receives both the current UTC datetime and `Europe/London` timezone in the system prompt, and returns execute_at set to approximately 17:00 local time converted to UTC

#### Scenario: Repeating task with relative start time
- **WHEN** a task is created with input "Every 30 minutes, check the server logs for errors" and the current UTC time is 2026-02-11T14:30:00Z
- **THEN** the LLM returns category `repeating`, repeat_interval `"30m"`, and execute_at set to approximately `2026-02-11T14:30:00Z` (now) for the first iteration

#### Scenario: System prompt includes datetime context
- **WHEN** `generate_title` is called with a task description and `now=datetime(2026, 2, 11, 14, 30, 0, tzinfo=timezone.utc)` and the timezone setting is `Europe/London`
- **THEN** the system prompt sent to the LLM contains the text "2026-02-11T14:30:00Z" and "Europe/London"

#### Scenario: Default timezone when not configured
- **WHEN** `generate_title` is called and no `timezone` setting exists in the database
- **THEN** the system prompt includes `UTC` as the timezone

#### Scenario: Repeating task with end date
- **WHEN** a task is created with input "Run the daily sales report every morning at 9am until the end of Q1 2026"
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `repeating`, execute_at set to tomorrow 9am, repeat_interval `"1d"`, and repeat_until set to approximately 2026-03-31

#### Scenario: LLM returns invalid JSON
- **WHEN** a task is created with a long input and the LLM returns a non-JSON response
- **THEN** the raw response is used as the title, category defaults to `immediate`, execute_at defaults to now, repeat_interval defaults to null, repeat_until defaults to null, and a "Needs Info" tag is applied

#### Scenario: LLM call fails
- **WHEN** a task is created with a long input and the LLM call fails or times out
- **THEN** the task is created with the first 5 words of the input plus "..." as the title, category `immediate`, execute_at set to current server time (as per immediate task rule), repeat_interval null, repeat_until null, and a "Needs Info" tag is applied

#### Scenario: LLM client not available
- **WHEN** a task is created with a long input but the OpenAI client was not initialized (missing env vars)
- **THEN** the task uses the fallback title (first 5 words + "..."), category `immediate`, execute_at set to current server time (as per immediate task rule), and gets a "Needs Info" tag

#### Scenario: Custom timeout from settings
- **WHEN** `generate_title` is called and the `llm_timeout` setting is `60`
- **THEN** the LLM chat completion call uses a 60-second timeout

#### Scenario: Default timeout when not configured
- **WHEN** `generate_title` is called and no `llm_timeout` setting exists in the database
- **THEN** the LLM chat completion call uses the default 30-second timeout
