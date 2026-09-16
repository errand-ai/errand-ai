## MODIFIED Requirements

### Requirement: Scalar field inheritance
For scalar profile fields (`model`, `system_prompt`, `max_turns`, `reasoning_effort`, `llm_timeout`), a non-null value SHALL override the corresponding global setting. A null value SHALL inherit the global setting. The `llm_timeout` field inherits from the global `task_processing_timeout` setting (default `30` seconds when no global value is set). The `max_turns` and `reasoning_effort` fields inherit from the resolved global `max_turns` and `reasoning_effort` settings (env → DB → default), and the resolved value SHALL be passed to every task runner container as `MAX_TURNS` / `REASONING_EFFORT`.

#### Scenario: Model overridden
- **WHEN** the profile has `model: "claude-haiku-4-5-20251001"` and the global `task_processing_model` is "claude-sonnet-4-5-20250929"
- **THEN** the resolved model is "claude-haiku-4-5-20251001"

#### Scenario: Model inherited
- **WHEN** the profile has `model: null`
- **THEN** the resolved model is the global `task_processing_model`

#### Scenario: System prompt overridden
- **WHEN** the profile has `system_prompt: "You are an email assistant"`
- **THEN** the resolved system prompt is "You are an email assistant" (replaces the global system prompt)

#### Scenario: Max turns overridden
- **WHEN** the profile has `max_turns: 10`
- **THEN** the MAX_TURNS environment variable is set to "10" for the container

#### Scenario: Max turns inherited from global setting
- **WHEN** the profile has `max_turns: null` and the global `max_turns` setting is stored as `75`
- **THEN** the MAX_TURNS environment variable is set to "75" for the container

#### Scenario: Max turns inherited and global setting absent
- **WHEN** the profile has `max_turns: null`, no `max_turns` setting is stored and `MAX_TURNS` is not set on the server
- **THEN** the MAX_TURNS environment variable is set to "200" for the container

#### Scenario: Reasoning effort overridden
- **WHEN** the profile has `reasoning_effort: "low"`
- **THEN** the REASONING_EFFORT environment variable is set to "low" for the container

#### Scenario: Reasoning effort inherited from server environment
- **WHEN** the profile has `reasoning_effort: null` and the server has `REASONING_EFFORT=high`
- **THEN** the REASONING_EFFORT environment variable is set to "high" for the container

#### Scenario: Reasoning effort inherited from global setting
- **WHEN** the profile has `reasoning_effort: null`, `REASONING_EFFORT` is not set on the server and the global `reasoning_effort` setting is stored as `low`
- **THEN** the REASONING_EFFORT environment variable is set to "low" for the container

#### Scenario: LLM timeout overridden by profile
- **WHEN** the profile has `llm_timeout: 300` and the global `task_processing_timeout` is `60`
- **THEN** the `LLM_REQUEST_TIMEOUT` environment variable is set to "300" for the container

#### Scenario: LLM timeout inherited from global setting
- **WHEN** the profile has `llm_timeout: null` and the global `task_processing_timeout` is `120`
- **THEN** the `LLM_REQUEST_TIMEOUT` environment variable is set to "120" for the container

#### Scenario: LLM timeout inherited and global setting absent
- **WHEN** the profile has `llm_timeout: null` and no `task_processing_timeout` setting exists in the database
- **THEN** the `LLM_REQUEST_TIMEOUT` environment variable is set to "30" for the container (built-in default)

## ADDED Requirements

### Requirement: Worker defaults report resolved values

`GET /api/worker/defaults` (admin only) SHALL return `{"max_turns": <string|null>, "reasoning_effort": <string|null>}`, where each value is the resolved global setting (env → DB → default), that is, the value a task with a null profile field actually receives. `max_turns` SHALL be serialised as a string, so the response shape is unchanged for existing clients.

#### Scenario: Database value reported
- **WHEN** `MAX_TURNS` is not set and the `max_turns` setting is stored as `75`
- **THEN** the response contains `"max_turns": "75"`

#### Scenario: Defaults reported when nothing is configured
- **WHEN** neither setting is stored and neither environment variable is set
- **THEN** the response is `{"max_turns": "200", "reasoning_effort": "medium"}`

#### Scenario: Environment value reported
- **WHEN** `REASONING_EFFORT=high` is set on the server
- **THEN** the response contains `"reasoning_effort": "high"` regardless of any stored value
