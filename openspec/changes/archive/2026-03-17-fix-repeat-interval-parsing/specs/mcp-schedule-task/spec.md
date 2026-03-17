## MODIFIED Requirements

### Requirement: schedule_task tool

The MCP server SHALL expose a `schedule_task` tool. The tool's docstring SHALL document the accepted `repeat_interval` formats with examples (e.g. `"15m"`, `"1h"`, `"1d"`, `"1w"`, `"7 days"`, `"daily"`, `"weekly"`). When `repeat_interval` is provided, the tool SHALL validate it by calling `parse_interval` before storing. If `parse_interval` returns None, the tool SHALL return an error message listing the accepted formats. If validation succeeds, the tool SHALL store the normalised compact form (e.g. `"7 days"` is stored as `"7d"`).

#### Scenario: Valid compact repeat_interval accepted

- **WHEN** a client calls `schedule_task` with `repeat_interval: "1w"`
- **THEN** the task is created with `repeat_interval = "1w"`

#### Scenario: Human-readable repeat_interval normalised and stored

- **WHEN** a client calls `schedule_task` with `repeat_interval: "7 days"`
- **THEN** the task is created with `repeat_interval = "7d"` (normalised compact form)

#### Scenario: Invalid repeat_interval rejected at write time

- **WHEN** a client calls `schedule_task` with `repeat_interval: "every other tuesday"`
- **THEN** the tool returns an error message listing accepted formats and does NOT create a task

#### Scenario: Tool description documents repeat_interval format

- **WHEN** an LLM reads the `schedule_task` tool schema
- **THEN** the tool description includes examples of accepted `repeat_interval` formats
