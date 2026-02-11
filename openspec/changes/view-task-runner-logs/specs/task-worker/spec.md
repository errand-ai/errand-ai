## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers
The worker SHALL execute each task by creating a container inside the DinD sidecar using the create->copy->start lifecycle. The worker SHALL: (1) pull the task runner image, (2) retrieve the `task_processing_model`, `system_prompt`, and `mcp_servers` settings from the database, (3) create the container from the task runner image with environment variables `OPENAI_BASE_URL`, `OPENAI_API_KEY` (from the worker's own environment), `OPENAI_MODEL` (from the `task_processing_model` setting, defaulting to `claude-sonnet-4-5-20250929`), `USER_PROMPT_PATH=/workspace/prompt.txt`, `SYSTEM_PROMPT_PATH=/workspace/system_prompt.txt`, and `MCP_CONFIGURATION_PATH=/workspace/mcp.json`, (4) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/system_prompt.txt` containing the system prompt from settings, `/workspace/mcp.json` containing the MCP server configuration from settings) into the stopped container via `put_archive()`, (5) start the container, (6) wait for the container to exit, (7) capture stdout/stderr via `container.logs()`, (8) parse the structured output from stdout, (9) store the structured result in the task's `output` field and stderr in the task's `runner_logs` field, (10) remove the container.

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

#### Scenario: WebSocket event includes all task fields
- **WHEN** the worker publishes a `task_updated` event after changing task status
- **THEN** the event payload includes all fields: id, title, description, status, position, category, execute_at, repeat_interval, repeat_until, output, runner_logs, retry_count, tags, created_at, and updated_at
