## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers
The worker SHALL execute each task by creating a container inside the DinD sidecar using the create->copy->start lifecycle. The worker SHALL: (1) pull the task runner image, (2) retrieve the `task_processing_model`, `system_prompt`, and `mcp_servers` settings from the database, (3) create the container from the task runner image with environment variables `OPENAI_BASE_URL`, `OPENAI_API_KEY` (from the worker's own environment), `OPENAI_MODEL` (from the `task_processing_model` setting, defaulting to `claude-sonnet-4-5-20250929`), `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, and `MCP_CONFIGURATION_PATH=/workspace/mcp.json`, (4) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/system_prompt.txt` containing the system prompt from settings, `/workspace/mcp.json` containing the MCP server configuration from settings **after environment variable substitution**) into the stopped container via `put_archive()`, (5) start the container, (6) wait for the container to exit, (7) capture stdout/stderr via `container.logs()`, (8) parse the structured output from stdout, (9) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (10) remove the container, (11) if the task completed successfully and has `category = 'repeating'`, attempt to reschedule by creating a cloned task (see `repeating-task-rescheduling` spec).

Before writing the `mcp_servers` configuration as `/workspace/mcp.json`, the worker SHALL perform environment variable substitution on all string values within the JSON structure. The substitution SHALL support two syntaxes: `$VARIABLE_NAME` and `${VARIABLE_NAME}`, where `VARIABLE_NAME` matches the pattern `[A-Za-z_][A-Za-z0-9_]*`. The worker SHALL resolve variable references against its own process environment (`os.environ`). If a referenced variable does not exist in the worker's environment, the placeholder SHALL be left unchanged in the output. Substitution SHALL only operate on string values within the JSON structure — keys, numbers, booleans, and nulls SHALL NOT be modified.

The worker SHALL store the captured stderr in the task's `runner_logs` field for all execution outcomes: successful completion, needs_input, retry on failure, and retry on parse error. The `runner_logs` field SHALL be written in every UPDATE statement that modifies the task after container execution.

The worker SHALL publish `task_updated` WebSocket events containing all task fields matching the API's `TaskResponse` schema: `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `output`, `runner_logs`, `retry_count`, `tags`, `created_at`, and `updated_at`. The `_task_to_dict()` helper SHALL serialise the complete task object including the `tags` relationship and the `runner_logs` field.

#### Scenario: Successful task execution stores logs separately
- **WHEN** the worker processes a pending task and the task runner exits with code 0 and stdout contains `{"status": "completed", "result": "Task done", "questions": []}` and stderr contains "2026-02-10 INFO Starting agent"
- **THEN** the worker stores "Task done" in the task's `output` field and "2026-02-10 INFO Starting agent" in the task's `runner_logs` field

#### Scenario: Task runner returns needs_input status with logs
- **WHEN** the worker processes a task and the task runner exits with code 0 and stdout contains `{"status": "needs_input", "result": "Need more details", "questions": ["What format?"]}` and stderr contains agent log output
- **THEN** the worker stores the output in the task's `output` field, stores stderr in `runner_logs`, moves the task to `review` status, and adds an "Input Needed" tag

#### Scenario: Task runner exits with non-zero code stores logs
- **WHEN** the worker processes a task and the task runner exits with a non-zero exit code with stderr containing error logs
- **THEN** the worker captures stderr in `runner_logs`, stores combined stdout/stderr in `output`, and schedules the task for retry

#### Scenario: Task runner stdout is not valid JSON stores logs
- **WHEN** the worker processes a task and the task runner exits with code 0 but stdout is not valid JSON and stderr contains log output
- **THEN** the worker stores stderr in `runner_logs`, stores combined output in `output`, and schedules the task for retry

#### Scenario: Container creation fails
- **WHEN** the worker attempts to create a container and the Docker API returns an error (e.g. image not found)
- **THEN** the worker schedules the task for retry with exponential backoff, logs the error, and continues polling

#### Scenario: Worker reads settings for task processing
- **WHEN** the worker picks up a new pending task
- **THEN** the worker queries the database for `task_processing_model`, `system_prompt`, and `mcp_servers` settings before creating the container

#### Scenario: Missing settings use defaults
- **WHEN** the worker picks up a task but `task_processing_model` is not set in settings
- **THEN** the worker uses `claude-sonnet-4-5-20250929` as the model and passes an empty string for system prompt and empty JSON object for MCP config

#### Scenario: Environment variable substitution in MCP config with $VAR syntax
- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains `{"mcpServers": {"argocd": {"url": "http://mcp-proxy:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer $LITELLM_API_KEY"}}}}` and the worker environment has `LITELLM_API_KEY=sk-secret-123`
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"argocd": {"url": "http://mcp-proxy:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer sk-secret-123"}}}}`

#### Scenario: Environment variable substitution in MCP config with ${VAR} syntax
- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"Authorization": "${AUTH_TOKEN}"}}}}` and the worker environment has `AUTH_TOKEN=Bearer abc-456`
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"Authorization": "Bearer abc-456"}}}}`

#### Scenario: Missing environment variable leaves placeholder unchanged
- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"x-api-key": "$MISSING_KEY"}}}}` and `MISSING_KEY` is not set in the worker environment
- **THEN** the `mcp.json` written to the container contains `{"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {"x-api-key": "$MISSING_KEY"}}}}`

#### Scenario: Substitution in nested JSON values
- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains nested objects with string values containing `$DB_PASSWORD` at various depths and the worker environment has `DB_PASSWORD=s3cret`
- **THEN** all string values containing `$DB_PASSWORD` at any nesting level are substituted with `s3cret`

#### Scenario: Non-string values are not modified during substitution
- **WHEN** the worker writes `mcp.json` and the `mcp_servers` configuration contains numeric, boolean, or null values
- **THEN** those values are passed through unchanged regardless of environment variables

#### Scenario: Multiple variables in a single string value
- **WHEN** the worker writes `mcp.json` and a string value contains `"$SCHEME://$HOST:$PORT/mcp"` and the worker environment has `SCHEME=https`, `HOST=api.example.com`, and `PORT=8443`
- **THEN** the substituted value is `"https://api.example.com:8443/mcp"`

#### Scenario: WebSocket event includes all task fields
- **WHEN** the worker publishes a `task_updated` event after changing task status
- **THEN** the event payload includes all fields: id, title, description, status, position, category, execute_at, repeat_interval, repeat_until, output, runner_logs, retry_count, tags, created_at, and updated_at

#### Scenario: Completed repeating task triggers rescheduling
- **WHEN** the worker moves a task with `category = 'repeating'` and `repeat_interval = '1h'` to `completed`
- **THEN** the worker calls the rescheduling logic which creates a new cloned task with `status = 'scheduled'` and `execute_at` approximately 1 hour from now

When the worker schedules a task for retry via `_schedule_retry`, it SHALL add a "Retry" tag to the task. If the "Retry" tag does not exist in the `tags` table, the worker SHALL create it. If the task already has the "Retry" tag, no duplicate association SHALL be created.

When the worker successfully processes a task (moves to `completed` or `review` status), it SHALL remove the "Retry" tag from the task if present. This ensures the tag does not persist on tasks that eventually succeed.

#### Scenario: Retry adds "Retry" tag
- **WHEN** the worker processes a task and the container exits with a non-zero exit code
- **THEN** the worker moves the task to `scheduled` status with exponential backoff and adds a "Retry" tag to the task

#### Scenario: Retry on unparseable output adds "Retry" tag
- **WHEN** the worker processes a task and the container exits with code 0 but stdout is not valid JSON
- **THEN** the worker moves the task to `scheduled` status and adds a "Retry" tag to the task

#### Scenario: Successful completion removes "Retry" tag
- **WHEN** the worker processes a task that has a "Retry" tag and the container exits with code 0 and valid structured output with status "completed"
- **THEN** the worker moves the task to `completed` status and removes the "Retry" tag

#### Scenario: Review status removes "Retry" tag
- **WHEN** the worker processes a task that has a "Retry" tag and the container exits with code 0 and valid structured output with status "needs_input"
- **THEN** the worker moves the task to `review` status, adds the "Input Needed" tag, and removes the "Retry" tag

#### Scenario: Retry tag created if not exists
- **WHEN** the worker schedules a task for retry and no "Retry" tag exists in the tags table
- **THEN** the worker creates the "Retry" tag and associates it with the task

#### Scenario: No duplicate retry tag
- **WHEN** the worker schedules a task for retry and the task already has a "Retry" tag from a previous retry
- **THEN** no duplicate tag association is created
