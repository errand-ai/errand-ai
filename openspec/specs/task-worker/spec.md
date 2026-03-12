## MODIFIED Requirements

### Requirement: Worker executes tasks via ContainerRuntime

The worker SHALL execute each task by delegating container operations to the configured `ContainerRuntime` implementation (see `container-runtime` spec). The worker SHALL: (1) retrieve the `task_processing_model` setting from the database as a `{"provider_id": "<uuid>", "model": "<model-id>"}` object, resolve the provider_id to a provider row in the `llm_provider` table, and read the decrypted `base_url` and `api_key` from that provider; also retrieve `system_prompt`, `mcp_servers`, `litellm_mcp_servers`, `ssh_private_key`, `git_ssh_hosts`, `hindsight_url`, `hindsight_bank_id`, and `hot_tools` settings, and query the `skills` and `skill_files` tables for all skills and their attached files, (1b) if the task has a non-null `profile_id`, read the corresponding `TaskProfile` row and apply profile overrides to the resolved settings using the inheritance rules: non-null scalar fields override globals, `null` list fields inherit all defaults, `[]` list fields clear to empty, non-empty list fields use only the specified subset, (2) if Playwright is configured, start the Playwright sidecar via the runtime-appropriate mechanism, (3) build the environment variables (`OPENAI_BASE_URL` set to the resolved provider's `base_url`, `OPENAI_API_KEY` set to the resolved provider's decrypted `api_key`, `OPENAI_MODEL` set to the resolved model ID, `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, `MCP_CONFIGURATION_PATH=/workspace/mcp.json`, and `HOT_TOOLS` set to the comma-separated hot tools list if configured) and input files, (4-15) all remaining steps (MCP injection, skills, SSH, Hindsight, GitHub, runtime prepare/run/result/cleanup, rescheduling) SHALL remain unchanged.

If the `task_processing_model` setting is empty, has a null `provider_id`, or references a provider that no longer exists, the worker SHALL log an error and mark the task as failed with output `{"error": "LLM provider not configured"}`.

If the task references a `profile_id` that no longer exists in the database (profile was deleted), the worker SHALL log a warning and proceed with default settings (as if `profile_id` were null).

#### Scenario: Worker resolves provider for task processing

- **WHEN** the worker dequeues a task and `task_processing_model` is `{"provider_id": "uuid-1", "model": "claude-sonnet-4-5-20250929"}`
- **THEN** the worker reads provider "uuid-1" from the `llm_provider` table, decrypts its API key, and passes `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` to the container

#### Scenario: Task processing model not configured

- **WHEN** the worker dequeues a task and `task_processing_model` is empty or has null provider_id
- **THEN** the worker marks the task as failed with `{"error": "LLM provider not configured"}`

#### Scenario: Task processing provider deleted

- **WHEN** the worker dequeues a task and `task_processing_model` references a provider_id not in the `llm_provider` table
- **THEN** the worker marks the task as failed with `{"error": "LLM provider not configured"}`

#### Scenario: Task with profile model override uses profile's provider

- **WHEN** the worker dequeues a task with a profile that overrides `task_processing_model` to `{"provider_id": "uuid-2", "model": "gpt-4o"}`
- **THEN** the worker uses provider "uuid-2" credentials and model "gpt-4o"

#### Scenario: Task with null profile uses global settings

- **WHEN** the worker dequeues a task with `profile_id = null`
- **THEN** the worker uses the global `task_processing_model` setting

#### Scenario: Worker passes HOT_TOOLS to task runner

- **WHEN** the worker dequeues a task and `hot_tools` setting is `"retain,recall,web_search"`
- **THEN** the worker sets `HOT_TOOLS=retain,recall,web_search` in the container environment variables

#### Scenario: HOT_TOOLS not configured

- **WHEN** the worker dequeues a task and no `hot_tools` setting exists
- **THEN** the worker does not set `HOT_TOOLS` in the container environment, allowing the task-runner to use its built-in defaults
