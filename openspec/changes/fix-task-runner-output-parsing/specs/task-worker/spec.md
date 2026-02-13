## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers
The worker SHALL parse the structured output from the task runner container's stdout using robust JSON extraction as a defence-in-depth measure. Before attempting `TaskRunnerOutput` validation, the worker SHALL apply the same extraction logic as the task runner: (1) try parsing the full stripped stdout as JSON, (2) locate a markdown code fence block anywhere in stdout and extract its contents, (3) find the first `{` and last `}` in stdout and extract that substring. The first strategy that produces valid JSON SHALL be used for `TaskRunnerOutput` validation. If no strategy produces valid JSON or the extracted JSON does not validate as a `TaskRunnerOutput`, the worker SHALL schedule the task for retry with the combined stdout/stderr stored in the output field and stderr in the runner_logs field.

The worker SHALL store the captured stderr in the task's `runner_logs` field for all execution outcomes: successful completion, needs_input, retry on failure, and retry on parse error. The `runner_logs` field SHALL be written in every UPDATE statement that modifies the task after container execution.

The worker SHALL publish `task_updated` WebSocket events containing all task fields matching the API's `TaskResponse` schema: `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `output`, `runner_logs`, `retry_count`, `tags`, `created_at`, and `updated_at`. The `_task_to_dict()` helper SHALL serialise the complete task object including the `tags` relationship and the `runner_logs` field.

#### Scenario: Successful task execution stores logs separately
- **WHEN** the worker processes a pending task and the task runner exits with code 0 and stdout contains `{"status": "completed", "result": "Task done", "questions": []}` and stderr contains "2026-02-10 INFO Starting agent"
- **THEN** the worker stores "Task done" in the task's `output` field and "2026-02-10 INFO Starting agent" in the task's `runner_logs` field

#### Scenario: Task runner stdout has preamble before JSON
- **WHEN** the worker processes a task and the task runner exits with code 0 and stdout contains `Here is the report:\n\n{"status": "completed", "result": "All healthy", "questions": []}`
- **THEN** the worker extracts the JSON from stdout, stores "All healthy" in the task's `output` field, and stores stderr in `runner_logs`

#### Scenario: Task runner stdout has preamble before JSON code fence
- **WHEN** the worker processes a task and the task runner exits with code 0 and stdout contains `Based on analysis...\n\n` followed by ```` ```json\n{"status": "completed", "result": "Report text", "questions": []}\n``` ````
- **THEN** the worker extracts the JSON from the code fence, stores "Report text" in the task's `output` field, and stores stderr in `runner_logs`

#### Scenario: Task runner returns needs_input status with logs
- **WHEN** the worker processes a task and the task runner exits with code 0 and stdout contains `{"status": "needs_input", "result": "Need more details", "questions": ["What format?"]}` and stderr contains agent log output
- **THEN** the worker stores the output in the task's `output` field, stores stderr in `runner_logs`, moves the task to `review` status, and adds an "Input Needed" tag

#### Scenario: Task runner exits with non-zero code stores logs
- **WHEN** the worker processes a task and the task runner exits with a non-zero exit code with stderr containing error logs
- **THEN** the worker captures stderr in `runner_logs`, stores combined stdout/stderr in `output`, and schedules the task for retry

#### Scenario: Task runner stdout is not valid JSON stores logs
- **WHEN** the worker processes a task and the task runner exits with code 0 but stdout contains no extractable valid JSON and stderr contains log output
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

#### Scenario: Completed repeating task triggers rescheduling
- **WHEN** the worker moves a task with `category = 'repeating'` and `repeat_interval = '1h'` to `completed`
- **THEN** the worker calls the rescheduling logic which creates a new cloned task with `status = 'scheduled'` and `execute_at` approximately 1 hour from now

When the worker schedules a task for retry via `_schedule_retry`, it SHALL add a "Retry" tag to the task. If the "Retry" tag does not exist in the `tags` table, the worker SHALL create it. If the task already has the "Retry" tag, no duplicate association SHALL be created.

When the worker successfully processes a task (moves to `completed` or `review` status), it SHALL remove the "Retry" tag from the task if present. This ensures the tag does not persist on tasks that eventually succeed.

#### Scenario: Retry adds "Retry" tag
- **WHEN** the worker processes a task and the container exits with a non-zero exit code
- **THEN** the worker moves the task to `scheduled` status with exponential backoff and adds a "Retry" tag to the task

#### Scenario: Retry on unparseable output adds "Retry" tag
- **WHEN** the worker processes a task and the container exits with code 0 but stdout contains no extractable valid JSON
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
