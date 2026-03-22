## MODIFIED Requirements

### Requirement: Tool call logging via RunHooks

_Extends existing requirement with turn tracking, timing, and httpx suppression._

The task runner SHALL suppress httpx INFO-level logging by setting `logging.getLogger("httpx").setLevel(logging.WARNING)` after `logging.basicConfig()`.

The `StreamEventEmitter` class SHALL maintain instance state:
- `_current_turn_id: str | None` — set on each `on_llm_start`, used to tag all events within that turn
- `_tool_start_times: dict[str, float]` — maps tool name to `time.monotonic()` start time

The `StreamEventEmitter` callbacks SHALL be modified as follows:

- `on_llm_start`: Generate a `turn_id` (`str(uuid4())[:8]`), store as `self._current_turn_id`, and emit `{"type": "llm_turn_start", "data": {"turn_id": "<id>", "model": "<MODEL_env_var>"}}`
- `on_llm_end`: No-op (turn boundary is marked by the next `on_llm_start`)
- `on_tool_start`: Record `time.monotonic()` in `self._tool_start_times[tool.name]`
- `on_tool_end`: Calculate `duration_ms` from stored start time, emit `tool_result` with `duration_ms` and `turn_id` fields added to the existing data payload

All events emitted from the streaming loop (`thinking`, `reasoning`, `tool_call`) SHALL include `"turn_id": self._current_turn_id` in their data payload when `_current_turn_id` is set.

#### Scenario: httpx INFO logging is suppressed

- **WHEN** the task runner starts and httpx would normally log `INFO HTTP Request: POST ...`
- **THEN** the log line is not emitted to stderr (httpx logger level is WARNING)

#### Scenario: LLM turn start event emitted

- **WHEN** `on_llm_start` fires
- **THEN** stderr contains `{"type": "llm_turn_start", "data": {"turn_id": "<8-char-uuid>", "model": "<model>"}}`

#### Scenario: Tool call event includes turn_id

- **WHEN** a `tool_called` stream event is received during a turn with `turn_id` "a1b2c3d4"
- **THEN** the emitted `tool_call` event includes `"turn_id": "a1b2c3d4"` in its data

#### Scenario: Thinking event includes turn_id

- **WHEN** a `message_output_item` stream event is received during a turn with `turn_id` "a1b2c3d4"
- **THEN** the emitted `thinking` event includes `"turn_id": "a1b2c3d4"` in its data

#### Scenario: Tool result includes duration_ms

- **WHEN** `on_tool_end` fires for a tool that took 1.5 seconds
- **THEN** the emitted `tool_result` event includes `"duration_ms": 1500`

#### Scenario: Tool result includes turn_id

- **WHEN** `on_tool_end` fires during a turn with `turn_id` "a1b2c3d4"
- **THEN** the emitted `tool_result` event includes `"turn_id": "a1b2c3d4"`

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
