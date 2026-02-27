## Purpose

Structured JSON event logging for agent lifecycle events (tool calls, results, reasoning) via RunHooks and stream events.

## Requirements

### Requirement: Tool call logging via RunHooks

The task runner SHALL log agent lifecycle events by emitting structured JSON events to stderr. The `ToolCallLogger` class (renamed to `StreamEventEmitter`) SHALL implement the following `RunHooks` callbacks:

- `on_agent_start`: Emit `{"type": "agent_start", "data": {"agent": "<agent_name>"}}` to stderr
- `on_tool_start`: No-op. The `tool_call` event is emitted from the streaming event loop (on `tool_called` events) instead, because hooks do not expose the full tool arguments
- `on_tool_end`: Emit `{"type": "tool_result", "data": {"tool": "<tool_name>", "output": "<truncated_result>", "length": <original_length>}}` to stderr
- `on_agent_end`: Emit `{"type": "agent_end", "data": {"output": <final_output>}}` to stderr
- `on_llm_start`: Log at DEBUG level for diagnostics (not emitted as a structured event)
- `on_llm_end`: Log at DEBUG level for diagnostics (not emitted as a structured event)

The `tool_call` event (`{"type": "tool_call", "data": {"tool": "<tool_name>", "args": <tool_args>}}`) SHALL be emitted from the `Runner.run_streamed()` event loop when a `tool_called` stream event is received, as the streaming API provides access to the full tool arguments (parsed from `raw_item.arguments`) that are not available in the `on_tool_start` hook.

The default maximum result length for `tool_result` output SHALL remain 500 characters. All events SHALL be written as single-line JSON to stderr.

#### Scenario: Agent start event emitted via hook

- **WHEN** the agent run begins and `on_agent_start` fires
- **THEN** stderr contains a JSON line with `"type": "agent_start"` and `"data": {"agent": "TaskRunner"}`

#### Scenario: Tool call event emitted with args via streaming loop

- **WHEN** the streaming event loop receives a `tool_called` event for `execute_command` with args `{"command": "git clone https://example.com/repo.git"}`
- **THEN** stderr contains a JSON line with `"type": "tool_call"` and `"data": {"tool": "execute_command", "args": {"command": "git clone https://example.com/repo.git"}}`

#### Scenario: Tool result event emitted with truncation

- **WHEN** a tool returns a result of 800 characters
- **THEN** stderr contains a JSON line with `"type": "tool_result"`, `"output"` truncated to 500 characters with `...` appended, and `"length": 800`

#### Scenario: Tool result event emitted without truncation

- **WHEN** a tool returns a result of 200 characters
- **THEN** stderr contains a JSON line with `"type": "tool_result"`, the full `"output"`, and `"length": 200`

#### Scenario: Agent end event emitted via hook

- **WHEN** the agent produces final output and `on_agent_end` fires
- **THEN** stderr contains a JSON line with `"type": "agent_end"` and `"data"` containing the output

#### Scenario: LLM start/end logged at debug level

- **WHEN** `on_llm_start` or `on_llm_end` fires
- **THEN** a DEBUG-level log message is written (visible only when LOG_LEVEL=DEBUG)

### Requirement: Post-run tool call summary

The task runner SHALL log a summary count of tool calls after the streaming run completes by counting `tool_call_output_item` entries in `result.new_items`. The summary SHALL be logged at INFO level to stderr (as a standard log line, not a structured event).

#### Scenario: Tool call summary is logged

- **WHEN** the agent streaming run completes and tool calls were made
- **THEN** a log line of the form `TOOL_SUMMARY total_tool_calls=<count>` is written to stderr at INFO level
