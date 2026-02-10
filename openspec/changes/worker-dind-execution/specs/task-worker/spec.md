## MODIFIED Requirements

### Requirement: Worker polls for pending tasks
The worker SHALL poll the database for tasks with status `pending` using `SELECT ... FOR UPDATE SKIP LOCKED` to safely dequeue a single task without contention with other workers. Tasks SHALL be dequeued in order of `position` ascending, with ties broken by `created_at` ascending, so that user-prioritised tasks are processed first.

#### Scenario: Task available
- **WHEN** the worker polls and a task with status `pending` exists
- **THEN** the worker acquires the task with the lowest position value, sets its status to `running`, and begins processing

#### Scenario: No tasks available
- **WHEN** the worker polls and no tasks have status `pending`
- **THEN** the worker waits for a configurable interval before polling again

#### Scenario: Multiple pending tasks with different positions
- **WHEN** the worker polls and tasks exist at positions 1, 3, and 5 in the Pending column
- **THEN** the worker acquires the task at position 1 (highest priority)

## ADDED Requirements

### Requirement: Worker connects to DinD on startup
The worker SHALL connect to the Docker daemon via the `DOCKER_HOST` environment variable using the Docker SDK for Python. On startup, the worker SHALL retry the connection with exponential backoff (starting at 1 second, up to 30 seconds) until the DinD daemon is ready. If the connection cannot be established after the retry period, the worker SHALL exit with an error.

#### Scenario: DinD ready on startup
- **WHEN** the worker starts and the DinD daemon is already running
- **THEN** the worker connects to Docker and begins polling for tasks

#### Scenario: DinD not yet ready
- **WHEN** the worker starts and the DinD daemon is still initialising
- **THEN** the worker retries the connection with exponential backoff until DinD responds

#### Scenario: DinD unreachable
- **WHEN** the worker starts and `DOCKER_HOST` is not set or the daemon cannot be reached after retries
- **THEN** the worker logs an error and exits with a non-zero exit code

### Requirement: Worker executes tasks in DinD containers
The worker SHALL execute each task by creating a container inside the DinD sidecar using the create→copy→start lifecycle. The worker SHALL: (1) create the container from the task runner image with credentials as environment variables, (2) copy input files (`/workspace/prompt.txt` containing the task description, `/workspace/mcp.json` containing the MCP server configuration) into the stopped container via `put_archive()`, (3) start the container, (4) wait for the container to exit, (5) capture stdout/stderr via `container.logs()`, (6) store the output in the task's `output` field, (7) remove the container.

#### Scenario: Successful task execution
- **WHEN** the worker processes a pending task with description "Fix the login bug"
- **THEN** the worker creates a container, copies `prompt.txt` (containing "Fix the login bug") and `mcp.json` into `/workspace/`, starts the container, waits for exit code 0, captures the output, stores it in the task's `output` field, and removes the container

#### Scenario: Task container fails
- **WHEN** the worker processes a task and the container exits with a non-zero exit code
- **THEN** the worker captures the output (including stderr), stores it in the task's `output` field, sets the task status to `failed`, and removes the container

#### Scenario: Container creation fails
- **WHEN** the worker attempts to create a container and the Docker API returns an error (e.g. image not found)
- **THEN** the worker sets the task status to `failed`, logs the error, and continues polling

### Requirement: Worker reads settings from database
The worker SHALL read the MCP server configuration and credentials from the `settings` table using the SQLAlchemy `Setting` model. The MCP configuration SHALL be read from the setting with key `mcp_servers`. The credentials SHALL be read from the setting with key `credentials` (a list of `{"key": "...", "value": "..."}` objects). If either setting does not exist, the worker SHALL use an empty default (empty JSON object for MCP, empty list for credentials).

#### Scenario: Settings exist
- **WHEN** the worker processes a task and `mcp_servers` and `credentials` settings exist in the database
- **THEN** the worker copies the MCP configuration as `/workspace/mcp.json` and passes the credentials as environment variables to the container

#### Scenario: No settings configured
- **WHEN** the worker processes a task and neither `mcp_servers` nor `credentials` settings exist
- **THEN** the worker copies an empty JSON object as `/workspace/mcp.json` and passes no extra environment variables to the container

### Requirement: Worker transitions completed tasks to review
After successful container execution (exit code 0), the worker SHALL set the task status to `review` and assign a new position at the bottom of the Review column. After failed execution (non-zero exit code), the worker SHALL set the task status to `failed`.

#### Scenario: Task succeeds
- **WHEN** a task container exits with code 0
- **THEN** the worker sets the task status to `review`, assigns the next position in the Review column, stores the captured output, and publishes a `task_updated` event

#### Scenario: Task fails
- **WHEN** a task container exits with a non-zero exit code
- **THEN** the worker sets the task status to `failed`, stores the captured output, and publishes a `task_updated` event

### Requirement: Worker truncates large output
The worker SHALL truncate captured container output to a configurable maximum size (default 1MB) before storing it in the database. If output is truncated, the worker SHALL append a marker indicating truncation.

#### Scenario: Output within limit
- **WHEN** a container produces 500KB of output and the limit is 1MB
- **THEN** the worker stores the full output without truncation

#### Scenario: Output exceeds limit
- **WHEN** a container produces 2MB of output and the limit is 1MB
- **THEN** the worker stores the first 1MB of output followed by a truncation marker
