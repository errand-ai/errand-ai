### Requirement: schedule_task tool

The MCP server SHALL expose a `schedule_task` tool that accepts the following parameters:
- `description` (string, required): The task description
- `execute_at` (string, required): ISO 8601 datetime string for when to first execute the task
- `repeat_interval` (string, optional): Repeat interval (e.g. `"15m"`, `"1h"`, `"1d"`, `"1w"`, or crontab like `"0 9 * * MON-FRI"`)
- `repeat_until` (string, optional): ISO 8601 datetime string for when to stop repeating

The tool SHALL create a new task with `status = "scheduled"` and `created_by = "mcp"`. The tool SHALL use the `generate_title()` LLM function to produce a short title from the description (falling back to the description if the description is 5 words or fewer, matching `new_task` behaviour). The tool SHALL NOT use the LLM-returned `category` — instead, it SHALL set `category = "repeating"` if `repeat_interval` is provided, otherwise `category = "scheduled"`. The tool SHALL parse `execute_at` and `repeat_until` using `datetime.fromisoformat()` and return a clear error if parsing fails. The tool SHALL return the UUID of the created task. The tool SHALL publish a `task_created` WebSocket event.

#### Scenario: Create a scheduled task

- **WHEN** a client calls `schedule_task` with `description: "Send weekly report"`, `execute_at: "2026-03-01T09:00:00Z"`
- **THEN** a new task is created with `status = "scheduled"`, `category = "scheduled"`, `execute_at` set to the parsed datetime, `repeat_interval = null`, `repeat_until = null`, and the UUID is returned

#### Scenario: Create a repeating task

- **WHEN** a client calls `schedule_task` with `description: "Check server health"`, `execute_at: "2026-03-01T09:00:00Z"`, `repeat_interval: "1h"`
- **THEN** a new task is created with `status = "scheduled"`, `category = "repeating"`, `execute_at` set to the parsed datetime, `repeat_interval = "1h"`, and the UUID is returned

#### Scenario: Create a repeating task with end date

- **WHEN** a client calls `schedule_task` with `description: "Daily standup reminder"`, `execute_at: "2026-03-01T09:00:00Z"`, `repeat_interval: "1d"`, `repeat_until: "2026-06-01T00:00:00Z"`
- **THEN** a new task is created with all timing fields set and `category = "repeating"`, and the UUID is returned

#### Scenario: Invalid execute_at format

- **WHEN** a client calls `schedule_task` with `execute_at: "next tuesday"`
- **THEN** the tool returns an error message indicating the datetime format is invalid

#### Scenario: Invalid repeat_until format

- **WHEN** a client calls `schedule_task` with a valid `execute_at` but `repeat_until: "forever"`
- **THEN** the tool returns an error message indicating the datetime format is invalid

#### Scenario: Title generation from long description

- **WHEN** a client calls `schedule_task` with a description longer than 5 words
- **THEN** the tool uses `generate_title()` to produce a short title and ignores the LLM-returned category

#### Scenario: Short description used as title directly

- **WHEN** a client calls `schedule_task` with `description: "Check logs"`
- **THEN** the task title is set to "Check logs" without calling the LLM
