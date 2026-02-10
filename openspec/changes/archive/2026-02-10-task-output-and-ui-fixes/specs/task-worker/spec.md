## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers
The worker SHALL execute each task by creating a container inside the DinD sidecar using the create->copy->start lifecycle. The worker SHALL: (1) pull the task runner image, (2) create the container from the task runner image with credentials as environment variables, (3) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/mcp.json` containing the MCP server configuration) into the stopped container via `put_archive()`, (4) start the container, (5) wait for the container to exit, (6) capture stdout/stderr via `container.logs()`, (7) store the output in the task's `output` field, (8) remove the container.

The worker SHALL publish `task_updated` WebSocket events containing all task fields matching the API's `TaskResponse` schema: `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `output`, `retry_count`, `tags`, `created_at`, and `updated_at`. The `_task_to_dict()` helper SHALL serialise the complete task object including the `tags` relationship.

#### Scenario: Successful task execution
- **WHEN** the worker processes a pending task with description "Fix the login bug"
- **THEN** the worker pulls the image, creates a container, copies `prompt.txt` (containing "Fix the login bug") and `mcp.json` into `/workspace/`, starts the container, waits for exit code 0, captures the output, stores it in the task's `output` field, and removes the container

#### Scenario: Task container fails
- **WHEN** the worker processes a task and the container exits with a non-zero exit code
- **THEN** the worker captures the output (including stderr), stores it in the task's `output` field, schedules the task for retry with exponential backoff, and removes the container

#### Scenario: Container creation fails
- **WHEN** the worker attempts to create a container and the Docker API returns an error (e.g. image not found)
- **THEN** the worker schedules the task for retry with exponential backoff, logs the error, and continues polling

#### Scenario: WebSocket event includes all task fields
- **WHEN** the worker publishes a `task_updated` event after changing task status
- **THEN** the event payload includes all fields: id, title, description, status, position, category, execute_at, repeat_interval, repeat_until, output, retry_count, tags, created_at, and updated_at
