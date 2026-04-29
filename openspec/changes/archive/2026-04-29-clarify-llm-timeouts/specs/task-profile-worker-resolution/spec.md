## MODIFIED Requirements

### Requirement: Scalar field inheritance
For scalar profile fields (`model`, `system_prompt`, `max_turns`, `reasoning_effort`, `llm_timeout`), a non-null value SHALL override the corresponding global setting. A null value SHALL inherit the global setting. The `llm_timeout` field inherits from the global `task_processing_timeout` setting (default `30` seconds when no global value is set).

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

#### Scenario: Reasoning effort overridden
- **WHEN** the profile has `reasoning_effort: "low"`
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

### Requirement: Worker propagates resolved LLM timeout to runner
For every task — whether a profile is attached or not — the worker SHALL set the `LLM_REQUEST_TIMEOUT` environment variable on the runner container. The value SHALL be the integer-second resolution of `profile.llm_timeout → task_processing_timeout setting → 30`.

#### Scenario: Task with no profile uses global default
- **WHEN** the worker dequeues a task with `profile_id = null` and `task_processing_timeout = 90`
- **THEN** the runner container is started with `LLM_REQUEST_TIMEOUT=90`

#### Scenario: Task with no profile and no global setting uses 30
- **WHEN** the worker dequeues a task with `profile_id = null` and no `task_processing_timeout` setting
- **THEN** the runner container is started with `LLM_REQUEST_TIMEOUT=30`

#### Scenario: Task with profile override
- **WHEN** the worker dequeues a task whose profile has `llm_timeout = 600`
- **THEN** the runner container is started with `LLM_REQUEST_TIMEOUT=600` regardless of the global setting
