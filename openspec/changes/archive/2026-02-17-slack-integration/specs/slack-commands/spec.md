## ADDED Requirements

### Requirement: Slack slash command endpoint
The backend SHALL expose `POST /slack/commands` that receives Slack slash command payloads. The endpoint SHALL be protected by the Slack request signature verification dependency. The endpoint SHALL parse the command text and dispatch to the appropriate handler based on the subcommand. The endpoint SHALL return Slack Block Kit JSON responses with `response_type: "ephemeral"` (visible only to the invoker) by default.

#### Scenario: Valid slash command received
- **WHEN** Slack posts a slash command payload to `/slack/commands` with valid signature
- **THEN** the command is parsed, dispatched, and a Block Kit response is returned

#### Scenario: Invalid signature rejected
- **WHEN** a request without a valid Slack signature is sent to `/slack/commands`
- **THEN** the endpoint returns HTTP 403

### Requirement: /task new command
The `/task new <title>` slash command SHALL create a new task with the provided title. The command SHALL use the same task creation logic as `POST /api/tasks` (including LLM title generation if available). The task's `created_by` field SHALL be set to the Slack user's resolved email address. The response SHALL be a Block Kit message showing the created task's title, ID (short prefix), status, and category.

#### Scenario: Create task from Slack
- **WHEN** a Slack user issues `/task new Write blog post about Kubernetes`
- **THEN** a task is created with title "Write blog post about Kubernetes", `created_by` set to the user's email, and a Block Kit confirmation is returned

#### Scenario: Missing title
- **WHEN** a Slack user issues `/task new` with no title text
- **THEN** an error response is returned: "Usage: `/task new <title>`"

### Requirement: /task status command
The `/task status <id>` slash command SHALL retrieve a task by UUID or UUID prefix and return its details. The response SHALL be a Block Kit message showing the task's title, status, category, created_at, updated_at, created_by, and updated_by.

#### Scenario: Get task status by full UUID
- **WHEN** a Slack user issues `/task status a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- **THEN** the task details are returned as a Block Kit message

#### Scenario: Get task status by short prefix
- **WHEN** a Slack user issues `/task status a1b2c3` and exactly one task matches the prefix
- **THEN** the matching task's details are returned

#### Scenario: Ambiguous prefix
- **WHEN** a Slack user issues `/task status a1b` and multiple tasks match the prefix
- **THEN** an error response lists the matching tasks and asks the user to be more specific

#### Scenario: Task not found
- **WHEN** a Slack user issues `/task status nonexistent`
- **THEN** an error response is returned: "No task found matching 'nonexistent'"

### Requirement: /task list command
The `/task list [status]` slash command SHALL list tasks, optionally filtered by status. The response SHALL be a Block Kit message showing tasks grouped by status with emoji indicators, limited to 20 tasks. If more tasks exist, a count of remaining tasks SHALL be shown.

#### Scenario: List all tasks
- **WHEN** a Slack user issues `/task list`
- **THEN** active tasks are returned grouped by status with emoji indicators

#### Scenario: List tasks filtered by status
- **WHEN** a Slack user issues `/task list pending`
- **THEN** only tasks with status "pending" are returned

#### Scenario: Empty task list
- **WHEN** a Slack user issues `/task list` and no active tasks exist
- **THEN** the response indicates no tasks found

#### Scenario: Large task list truncated
- **WHEN** more than 20 active tasks exist
- **THEN** the response shows the first 20 and indicates how many more exist

### Requirement: /task run command
The `/task run <id>` slash command SHALL queue a task for execution by setting its status to "pending". The command SHALL verify the task exists and is in a valid state to run (not already running or pending). The task's `updated_by` field SHALL be set to the Slack user's resolved email. The response SHALL confirm the task was queued.

#### Scenario: Queue a task for execution
- **WHEN** a Slack user issues `/task run a1b2c3` for a task in "new" status
- **THEN** the task status is set to "pending", `updated_by` is set to the user's email, and a confirmation is returned

#### Scenario: Task already running
- **WHEN** a Slack user issues `/task run a1b2c3` for a task in "running" status
- **THEN** an error response is returned: "Task is already running"

#### Scenario: Task not found
- **WHEN** a Slack user issues `/task run nonexistent`
- **THEN** an error response is returned: "No task found matching 'nonexistent'"

### Requirement: /task output command
The `/task output <id>` slash command SHALL retrieve a task's output. If the task has output, it SHALL be displayed in a Block Kit code block. If the output exceeds 2900 characters (Slack's block text limit), it SHALL be truncated with a message indicating the output was truncated. If the task has no output, the current status SHALL be shown.

#### Scenario: Task with output
- **WHEN** a Slack user issues `/task output a1b2c3` for a completed task with output
- **THEN** the output is displayed in a code block

#### Scenario: Task output truncated
- **WHEN** a task's output exceeds 2900 characters
- **THEN** the output is truncated with "... (truncated — view full output in web UI)"

#### Scenario: Task without output
- **WHEN** a Slack user issues `/task output a1b2c3` for a task in "new" status with no output
- **THEN** the response shows "Task is in status 'new' — no output yet"

### Requirement: Unknown subcommand help
When an unrecognized subcommand is given (e.g., `/task foo`) or no subcommand is given (e.g., `/task`), the endpoint SHALL return a help message listing available subcommands and their usage.

#### Scenario: Unknown subcommand
- **WHEN** a Slack user issues `/task foo`
- **THEN** a help message is returned listing available subcommands: `new`, `status`, `list`, `run`, `output`

#### Scenario: Empty command
- **WHEN** a Slack user issues `/task` with no arguments
- **THEN** a help message is returned listing available subcommands

### Requirement: Status emoji mapping
Block Kit responses SHALL use emoji indicators for task statuses: new (white_circle), scheduled (clock3), pending (hourglass_flowing_sand), running (gear), review (eyes), completed (white_check_mark), archived (file_cabinet), deleted (wastebasket).

#### Scenario: Task status rendered with emoji
- **WHEN** a task with status "running" is displayed in a Block Kit response
- **THEN** the status is rendered as ":gear: running"
