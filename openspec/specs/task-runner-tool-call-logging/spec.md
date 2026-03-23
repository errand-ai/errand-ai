## Purpose

Structured JSON event logging for agent lifecycle events (tool calls, results, reasoning) via RunHooks and stream events, with turn-based grouping and tool timing.

## Requirements

### Requirement: Tool call logging via RunHooks

The task runner SHALL suppress httpx INFO-level logging by setting `logging.getLogger("httpx").setLevel(logging.WARNING)` after `logging.basicConfig()`.

The task runner SHALL log agent lifecycle events by emitting structured JSON events to stderr. The `StreamEventEmitter` class SHALL implement the following `RunHooks` callbacks:

- `on_agent_start`: Emit `{"type": "agent_start", "data": {"agent": "<agent_name>"}}` to stderr
- `on_tool_start`: Record `time.monotonic()` in `self._tool_start_times[tool.name]` for duration tracking
- `on_tool_end`: Calculate `duration_ms` from stored start time, emit `{"type": "tool_result", "data": {"tool": "<tool_name>", "output": "<truncated_result>", "length": <original_length>, "duration_ms": <ms>, "turn_id": "<turn_id>"}}` to stderr. `duration_ms` and `turn_id` are omitted when not available.
- `on_agent_end`: Emit `{"type": "agent_end", "data": {"output": <final_output>}}` to stderr
- `on_llm_start`: Generate a `turn_id` (`str(uuid4())[:8]`), store as `self._current_turn_id`, and emit `{"type": "llm_turn_start", "data": {"turn_id": "<id>", "model": "<OPENAI_MODEL_or_MODEL_env_var>"}}`
- `on_llm_end`: No-op (turn boundary is marked by the next `on_llm_start`)

The `StreamEventEmitter` class SHALL maintain instance state:
- `_current_turn_id: str | None` — set on each `on_llm_start`, used to tag all events within that turn
- `_tool_start_times: dict[str, float]` — maps tool name to `time.monotonic()` start time

The `tool_call` event (`{"type": "tool_call", "data": {"tool": "<tool_name>", "args": <tool_args>, "turn_id": "<turn_id>"}}`) SHALL be emitted from the `Runner.run_streamed()` event loop when a `tool_called` stream event is received, as the streaming API provides access to the full tool arguments (parsed from `raw_item.arguments`) that are not available in the `on_tool_start` hook.

All events emitted from the streaming loop (`thinking`, `reasoning`, `tool_call`) SHALL include `"turn_id"` in their data payload when `_current_turn_id` is set. When `_current_turn_id` is not set, `turn_id` SHALL be omitted (not set to empty string).

The default maximum result length for `tool_result` output SHALL remain 500 characters. All events SHALL be written as single-line JSON to stderr.

#### Scenario: httpx INFO logging is suppressed

- **WHEN** the task runner starts and httpx would normally log `INFO HTTP Request: POST ...`
- **THEN** the log line is not emitted to stderr (httpx logger level is WARNING)

#### Scenario: Agent start event emitted via hook

- **WHEN** the agent run begins and `on_agent_start` fires
- **THEN** stderr contains a JSON line with `"type": "agent_start"` and `"data": {"agent": "TaskRunner"}`

#### Scenario: LLM turn start event emitted

- **WHEN** `on_llm_start` fires
- **THEN** stderr contains `{"type": "llm_turn_start", "data": {"turn_id": "<8-char-uuid>", "model": "<model>"}}`

#### Scenario: Tool call event emitted with args and turn_id via streaming loop

- **WHEN** the streaming event loop receives a `tool_called` event for `execute_command` with args `{"command": "git clone https://example.com/repo.git"}` during a turn with `turn_id` "a1b2c3d4"
- **THEN** stderr contains a JSON line with `"type": "tool_call"` and `"data": {"tool": "execute_command", "args": {"command": "git clone https://example.com/repo.git"}, "turn_id": "a1b2c3d4"}`

#### Scenario: Thinking event includes turn_id

- **WHEN** a `message_output_item` stream event is received during a turn with `turn_id` "a1b2c3d4"
- **THEN** the emitted `thinking` event includes `"turn_id": "a1b2c3d4"` in its data

#### Scenario: Tool result event emitted with truncation, duration, and turn_id

- **WHEN** a tool returns a result of 800 characters after 1.5 seconds during a turn with `turn_id` "a1b2c3d4"
- **THEN** stderr contains a JSON line with `"type": "tool_result"`, `"output"` truncated to 500 characters with `...` appended, `"length": 800`, `"duration_ms": 1500`, and `"turn_id": "a1b2c3d4"`

#### Scenario: Tool result event emitted without truncation

- **WHEN** a tool returns a result of 200 characters
- **THEN** stderr contains a JSON line with `"type": "tool_result"`, the full `"output"`, and `"length": 200`

#### Scenario: Tool result omits duration_ms when no start time

- **WHEN** `on_tool_end` fires for a tool where `on_tool_start` was not called
- **THEN** the emitted `tool_result` event does not include `"duration_ms"`

#### Scenario: Tool result omits turn_id when no turn active

- **WHEN** `on_tool_end` fires and no `on_llm_start` has been called
- **THEN** the emitted `tool_result` event does not include `"turn_id"`

#### Scenario: Agent end event emitted via hook

- **WHEN** the agent produces final output and `on_agent_end` fires
- **THEN** stderr contains a JSON line with `"type": "agent_end"` and `"data"` containing the output

### Requirement: MCP connected summary event

After all MCP servers are initialized, the task runner SHALL emit a single structured event:
`{"type": "mcp_connected", "data": {"servers": ["<name1>", "<name2>", ...], "count": <N>}}`

This replaces the raw httpx log lines for MCP connection handshakes (suppressed by the httpx logging change).

#### Scenario: MCP connected event emitted after initialization

- **WHEN** all MCP servers have been connected successfully
- **THEN** stderr contains a single `mcp_connected` event listing all server names and their count

#### Scenario: MCP connected event reflects actual servers

- **WHEN** 8 MCP servers are configured and connected
- **THEN** the `mcp_connected` event has `"count": 8` and `"servers"` contains exactly 8 names

### Requirement: Post-run tool call summary

The task runner SHALL log a summary count of tool calls after the streaming run completes by counting `tool_call_output_item` entries in `result.new_items`. The summary SHALL be logged at INFO level to stderr (as a standard log line, not a structured event).

#### Scenario: Tool call summary is logged

- **WHEN** the agent streaming run completes and tool calls were made
- **THEN** a log line of the form `TOOL_SUMMARY total_tool_calls=<count>` is written to stderr at INFO level
