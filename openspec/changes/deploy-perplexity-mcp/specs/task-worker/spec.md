## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

The worker SHALL execute each task by creating a container inside the DinD sidecar using the create->copy->start lifecycle. The worker SHALL: (1) pull the task runner image, (2) retrieve the `task_processing_model`, `system_prompt`, and `mcp_servers` settings from the database, (3) create the container from the task runner image with environment variables `OPENAI_BASE_URL`, `OPENAI_API_KEY` (from the worker's own environment), `OPENAI_MODEL` (from the `task_processing_model` setting, defaulting to `claude-sonnet-4-5-20250929`), `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, and `MCP_CONFIGURATION_PATH=/workspace/mcp.json`, (4) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/system_prompt.txt` containing the system prompt from settings, `/workspace/mcp.json` containing the MCP server configuration from settings) into the stopped container via `put_archive()`, (5) start the container, (6) wait for the container to exit, (7) capture stdout/stderr via `container.logs()`, (8) parse the structured output from stdout, (9) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (10) remove the container, (11) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task (see `repeating-task-rescheduling` spec).

Before writing `mcp.json`, the worker SHALL check whether the `USE_PERPLEXITY` environment variable is set to `"true"`. If so, the worker SHALL inject a `"perplexity-ask"` entry into the `mcpServers` object of the MCP configuration with the value `{"url": "$PERPLEXITY_URL"}`. This injection SHALL occur before the existing `substitute_env_vars()` call, so that `$PERPLEXITY_URL` is resolved to the actual service URL. If the MCP configuration from the database already contains a `"perplexity-ask"` key, the database value SHALL take precedence (the injected entry SHALL NOT overwrite it).

When `USE_PERPLEXITY` is `"true"`, the worker SHALL also append a Perplexity usage instruction block to the system prompt before writing `system_prompt.txt` into the container. The instruction block SHALL be appended after the admin-configured system prompt content (separated by two newlines) and SHALL instruct the LLM that it has access to the `perplexity-ask` MCP tool for looking up current information online, conducting web research, or reasoning about topics that require context beyond its training data.

The worker SHALL store the captured stderr in the task's `runner_logs` field for all execution outcomes: successful completion, needs_input, retry on failure, and retry on parse error. The `runner_logs` field SHALL be written in every UPDATE statement that modifies the task after container execution.

The worker SHALL publish `task_updated` WebSocket events containing all task fields matching the API's `TaskResponse` schema: `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `output`, `runner_logs`, `retry_count`, `tags`, `created_at`, and `updated_at`. The `_task_to_dict()` helper SHALL serialise the complete task object including the `tags` relationship and the `runner_logs` field.

#### Scenario: Successful task execution stores logs separately

- **WHEN** the worker processes a pending task and the task runner exits with code 0 and stdout contains `{"status": "completed", "result": "Task done", "questions": []}` and stderr contains "2026-02-10 INFO Starting agent"
- **THEN** the worker stores "Task done" in the task's `output` field and "2026-02-10 INFO Starting agent" in the task's `runner_logs` field

#### Scenario: Perplexity injected into mcp.json when enabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is set to `"true"` and `PERPLEXITY_URL` is set to `"http://cm-perplexity-mcp:8000/sse"` and the database `mcp_servers` setting is `{"mcpServers": {"other": {"url": "http://other/mcp"}}}`
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"perplexity-ask": {"url": "http://cm-perplexity-mcp:8000/sse"}, "other": {"url": "http://other/mcp"}}}`

#### Scenario: System prompt augmented when Perplexity enabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is set to `"true"` and the admin system prompt is `"You are a helpful assistant."`
- **THEN** the `system_prompt.txt` written to the container contains the original prompt followed by an instruction block explaining the `perplexity-ask` tool is available for web search and current information lookups

#### Scenario: System prompt unchanged when Perplexity disabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is not set or is not `"true"` and the admin system prompt is `"You are a helpful assistant."`
- **THEN** the `system_prompt.txt` written to the container contains exactly `"You are a helpful assistant."` with no additions

#### Scenario: Perplexity not injected when disabled

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is not set or is not `"true"`
- **THEN** the `mcp.json` written to the container contains only the MCP servers from the database setting, unchanged

#### Scenario: Database perplexity entry takes precedence

- **WHEN** the worker processes a task and `USE_PERPLEXITY` is set to `"true"` and the database `mcp_servers` setting already contains a `"perplexity-ask"` key with `{"url": "http://custom-perplexity/mcp"}`
- **THEN** the `mcp.json` written to the container uses the database value `{"url": "http://custom-perplexity/mcp"}` for the `"perplexity-ask"` key, not the injected one
