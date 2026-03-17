## Purpose

MCP tool for creating scheduled and repeating tasks with optional task profile assignment.

## Requirements

### Requirement: schedule_task tool
The MCP server SHALL expose a `schedule_task` tool that accepts the following parameters:
- `description` (string, required): The task description
- `execute_at` (string, required): ISO 8601 datetime string for when to first execute the task
- `repeat_interval` (string, optional): Repeat interval in compact format (`"15m"`, `"1h"`, `"1d"`, `"1w"`) or human-readable (`"7 days"`, `"2 hours"`, `"daily"`, `"weekly"`, `"hourly"`)
- `repeat_until` (string, optional): ISO 8601 datetime string for when to stop repeating
- `profile` (string, optional): Name of a task profile to assign

The tool's docstring SHALL document the accepted `repeat_interval` formats with examples. The tool SHALL create a new task with `status = "scheduled"` and `created_by = "mcp"`. The tool SHALL use the `generate_title()` LLM function to produce a short title from the description (falling back to the description if the description is 5 words or fewer, matching `new_task` behaviour). The tool SHALL NOT use the LLM-returned `category` — instead, it SHALL set `category = "repeating"` if `repeat_interval` is provided, otherwise `category = "scheduled"`. When `repeat_interval` is provided, the tool SHALL validate it by calling `normalize_interval` before storing. If normalisation returns None, the tool SHALL return an error message listing the accepted formats. If validation succeeds, the tool SHALL store the normalised compact form (e.g. `"7 days"` is stored as `"7d"`). If `profile` is provided, the tool SHALL look up the `TaskProfile` by name and set `profile_id` to its UUID. If the profile name is not found, the tool SHALL return an error. The tool SHALL parse `execute_at` and `repeat_until` using `datetime.fromisoformat()` and return a clear error if parsing fails. The tool SHALL return the UUID of the created task. The tool SHALL publish a `task_created` WebSocket event.

#### Scenario: Create a scheduled task without profile
- **WHEN** a client calls `schedule_task` with `description: "Send weekly report"`, `execute_at: "2026-03-01T09:00:00Z"`
- **THEN** a new task is created with `status = "scheduled"`, `category = "scheduled"`, `profile_id = null`, and the UUID is returned

#### Scenario: Create a repeating task with profile
- **WHEN** a client calls `schedule_task` with `description: "Check inbox"`, `execute_at: "2026-03-01T09:00:00Z"`, `repeat_interval: "15m"`, `profile: "email-triage"`
- **THEN** a new task is created with `category = "repeating"`, `profile_id` set to the email-triage profile's UUID, and the UUID is returned

#### Scenario: Unknown profile name
- **WHEN** a client calls `schedule_task` with `profile: "nonexistent"`
- **THEN** the tool returns an error message: "Error: Task profile 'nonexistent' not found."

#### Scenario: Create a repeating task without profile
- **WHEN** a client calls `schedule_task` with `description: "Check server health"`, `execute_at: "2026-03-01T09:00:00Z"`, `repeat_interval: "1h"` and no `profile` parameter
- **THEN** a new task is created with `profile_id = null`

#### Scenario: Invalid execute_at format
- **WHEN** a client calls `schedule_task` with `execute_at: "next tuesday"`
- **THEN** the tool returns an error message indicating the datetime format is invalid

#### Scenario: Short description used as title directly
- **WHEN** a client calls `schedule_task` with `description: "Check logs"`
- **THEN** the task title is set to "Check logs" without calling the LLM

#### Scenario: Human-readable repeat_interval normalised and stored
- **WHEN** a client calls `schedule_task` with `repeat_interval: "7 days"`
- **THEN** the task is created with `repeat_interval = "7d"` (normalised compact form)

#### Scenario: Invalid repeat_interval rejected at write time
- **WHEN** a client calls `schedule_task` with `repeat_interval: "every other tuesday"`
- **THEN** the tool returns an error message listing accepted formats and does NOT create a task

#### Scenario: Tool description documents repeat_interval format
- **WHEN** an LLM reads the `schedule_task` tool schema
- **THEN** the tool description includes examples of accepted `repeat_interval` formats
