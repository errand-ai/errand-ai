## MODIFIED Requirements

### Requirement: LLM title generation from task description
When a new task is created with an input longer than 5 words, the backend SHALL call the LLM to generate a short title (2-5 words), categorise the task as `immediate`, `scheduled`, or `repeating`, and extract timing information. The LLM call SHALL use the `chat.completions.create` method with the model from the `llm_model` setting (default: `claude-haiku-4-5-20251001`). The system prompt SHALL instruct the model to return a JSON object with fields: `title` (string, 2-5 words), `category` (immediate|scheduled|repeating), `execute_at` (ISO 8601 datetime string or null), `repeat_interval` (string like "15m", "1h", "1d", or crontab expression, or null), `repeat_until` (ISO 8601 datetime string or null). The call SHALL have a 5-second timeout.

#### Scenario: Successful title and categorisation
- **WHEN** a task is created with input "The login page throws a 500 error when users with special characters try to reset their password"
- **THEN** the backend calls the LLM and receives a JSON response with title, category `immediate`, execute_at set to approximately now, and repeat_interval null

#### Scenario: Scheduled task categorisation
- **WHEN** a task is created with input "Send the quarterly financial report to the board at 5pm today"
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `scheduled`, execute_at set to 5pm today (UTC), and repeat_interval null

#### Scenario: Repeating task categorisation
- **WHEN** a task is created with input "Check the production server health dashboard every 30 minutes and report any anomalies"
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `repeating`, execute_at set to approximately now, repeat_interval `"30m"`, and repeat_until null

#### Scenario: Repeating task with end date
- **WHEN** a task is created with input "Run the daily sales report every morning at 9am until the end of Q1 2026"
- **THEN** the backend calls the LLM and receives a JSON response with a title, category `repeating`, execute_at set to tomorrow 9am, repeat_interval `"1d"`, and repeat_until set to approximately 2026-03-31

#### Scenario: LLM returns invalid JSON
- **WHEN** a task is created with a long input and the LLM returns a non-JSON response
- **THEN** the raw response is used as the title, category defaults to `immediate`, execute_at defaults to now, repeat_interval defaults to null, repeat_until defaults to null, and a "Needs Info" tag is applied

#### Scenario: LLM call fails
- **WHEN** a task is created with a long input and the LLM call fails or times out
- **THEN** the task is created with the first 5 words of the input plus "..." as the title, category `immediate`, execute_at null, repeat_interval null, repeat_until null, and a "Needs Info" tag is applied

#### Scenario: LLM client not available
- **WHEN** a task is created with a long input but the OpenAI client was not initialized (missing env vars)
- **THEN** the task uses the fallback title (first 5 words + "..."), category `immediate`, and gets a "Needs Info" tag
