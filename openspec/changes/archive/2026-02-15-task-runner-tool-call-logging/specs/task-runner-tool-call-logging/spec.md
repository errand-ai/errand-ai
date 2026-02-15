## ADDED Requirements

### Requirement: Tool call logging via RunHooks

The task runner SHALL log all tool calls in real-time by passing a `ToolCallLogger` subclass of `RunHooks` to `Runner.run()`. The `on_tool_start` hook SHALL log the tool name. The `on_tool_end` hook SHALL log the tool name and a truncated result. The default maximum result length SHALL be 500 characters. All log messages SHALL be written to stderr via the Python `logging` module at INFO level. Both local function tools and MCP tools (which the SDK converts to FunctionTools) SHALL be logged through the same hooks.

#### Scenario: Tool call is logged on start

- **WHEN** the agent invokes any tool (local or MCP)
- **THEN** a log line of the form `TOOL_CALL [<tool_name>]` is written to stderr

#### Scenario: Tool result is logged on end

- **WHEN** a tool returns a result
- **THEN** a log line of the form `TOOL_RESULT [<tool_name>] (<length> chars): <truncated_result>` is written to stderr

#### Scenario: Long tool results are truncated

- **WHEN** a tool result exceeds 500 characters
- **THEN** the logged result is truncated to 500 characters with `...` appended

### Requirement: Post-run tool call summary

The task runner SHALL log a summary count of tool calls after `Runner.run()` completes by counting `ToolCallOutputItem` entries in `result.new_items`.

#### Scenario: Tool call summary is logged

- **WHEN** the agent run completes and tool calls were made
- **THEN** a log line of the form `TOOL_SUMMARY total_tool_calls=<count>` is written to stderr

### Requirement: Tool call log format

All tool call log lines SHALL use the prefix `TOOL_CALL` for invocations and `TOOL_RESULT` for results. The tool name SHALL appear in square brackets immediately after the prefix. This format SHALL be consistent across all tool types to allow grepping for tool activity in runner_logs.

#### Scenario: Log lines are greppable

- **WHEN** runner_logs are searched for `TOOL_CALL` or `TOOL_RESULT`
- **THEN** all tool invocations and their results are returned regardless of tool type
