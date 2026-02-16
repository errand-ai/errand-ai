## ADDED Requirements

### Requirement: Structured event protocol on task runner stderr

The task runner SHALL emit structured JSON events to stderr, one JSON object per line. Each event SHALL have a `type` field (string) and a `data` field (object). The following event types SHALL be supported:

| Type | Data fields | Description |
|------|-------------|-------------|
| `agent_start` | `agent` (string) | Agent loop has begun |
| `thinking` | `text` (string) | Model's intermediate text output between tool calls |
| `reasoning` | `text` (string) | Reasoning/thinking summary from a ReasoningItem |
| `tool_call` | `tool` (string), `args` (object) | Tool invocation starting |
| `tool_result` | `tool` (string), `output` (string), `length` (integer) | Tool returned a result |
| `agent_end` | `output` (object) | Agent produced final structured output |
| `error` | `message` (string) | Error during execution |

The `tool_result` event's `output` field SHALL be truncated to a maximum of 500 characters. The `length` field SHALL contain the original untruncated length.

#### Scenario: Agent start event emitted

- **WHEN** the task runner begins the agent streaming loop
- **THEN** stderr contains a line `{"type": "agent_start", "data": {"agent": "TaskRunner"}}`

#### Scenario: Thinking event emitted for model text

- **WHEN** the agent produces intermediate text output (a `MessageOutputItem`) that is not the final output
- **THEN** stderr contains a line `{"type": "thinking", "data": {"text": "<model text>"}}`

#### Scenario: Reasoning event emitted when model supports it

- **WHEN** the stream produces a `ReasoningItem` (model supports extended thinking)
- **THEN** stderr contains a line `{"type": "reasoning", "data": {"text": "<reasoning summary>"}}`

#### Scenario: No reasoning events when model does not support it

- **WHEN** the stream completes without producing any `ReasoningItem` objects
- **THEN** no `reasoning` events appear on stderr (the absence is not an error)

#### Scenario: Tool call event emitted

- **WHEN** the agent invokes a tool named `execute_command` with args `{"command": "ls -la"}`
- **THEN** stderr contains a line `{"type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls -la"}}}`

#### Scenario: Tool result event emitted with truncation

- **WHEN** a tool returns a result of 1200 characters
- **THEN** stderr contains a line with `"type": "tool_result"`, `"output"` truncated to 500 characters with `...` appended, and `"length": 1200`

#### Scenario: Tool result event emitted without truncation

- **WHEN** a tool returns a result of 200 characters
- **THEN** stderr contains a line with `"type": "tool_result"`, the full `"output"`, and `"length": 200`

#### Scenario: Agent end event emitted

- **WHEN** the agent produces its final structured output
- **THEN** stderr contains a line `{"type": "agent_end", "data": {"output": <TaskRunnerOutput object>}}`

#### Scenario: Error event emitted

- **WHEN** the agent encounters an error during execution
- **THEN** stderr contains a line `{"type": "error", "data": {"message": "<error description>"}}`

#### Scenario: All events are valid JSON

- **WHEN** any event is emitted to stderr
- **THEN** the line is parseable as valid JSON with exactly `type` (string) and `data` (object) top-level keys

### Requirement: Valkey message format for structured events

The worker SHALL publish structured events to the per-task Valkey pub/sub channel `task_logs:{task_id}` using the format `{"event": "task_event", "type": "<event_type>", "data": <event_data>}`. The `task_log_end` sentinel SHALL remain as `{"event": "task_log_end"}`.

#### Scenario: Structured event published to Valkey

- **WHEN** the worker reads a stderr line `{"type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}`
- **THEN** the worker publishes `{"event": "task_event", "type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}` to the `task_logs:{task_id}` channel

#### Scenario: Non-JSON stderr lines published as raw events

- **WHEN** the worker reads a stderr line that is not valid JSON (e.g., a Python traceback or library log message)
- **THEN** the worker publishes `{"event": "task_event", "type": "raw", "data": {"line": "<raw stderr line>"}}` to the Valkey channel

#### Scenario: End sentinel unchanged

- **WHEN** the task runner container exits
- **THEN** the worker publishes `{"event": "task_log_end"}` to the Valkey channel (same format as before)

### Requirement: Rich log viewer rendering in TaskLogModal

The `TaskLogModal` component SHALL render structured events with distinct visual treatments based on event type:

- **`thinking`**: Displayed in an italic, muted-colour block. Collapsible when the text exceeds 3 lines, collapsed by default.
- **`reasoning`**: Displayed in a distinct styled block (e.g., indented with a left border accent). Collapsible when the text exceeds 3 lines, collapsed by default.
- **`tool_call`**: Displayed as a collapsible card. The header SHALL show the tool name and be always visible. The body SHALL show the args formatted as JSON. Collapsed by default.
- **`tool_result`**: Appended to the preceding `tool_call` card as a result section. SHALL show the output length. If the output exceeds 3 lines, it SHALL be collapsed by default. Output SHALL use a monospace font.
- **`agent_start`**: Displayed as a subtle status line (e.g., "Agent started").
- **`agent_end`**: Displayed as a subtle status line (e.g., "Agent completed").
- **`error`**: Displayed as a red-styled alert block with the error message.
- **`raw`**: Displayed as a plain monospace text line (fallback for non-JSON stderr).

The log viewer SHALL maintain auto-scroll behaviour (scroll to bottom as new events arrive) unless the user has manually scrolled up.

#### Scenario: Tool call rendered as collapsible card

- **WHEN** the log viewer receives a `tool_call` event with tool `execute_command` and args `{"command": "git status"}`
- **THEN** the viewer displays a collapsible card with header "execute_command" and expandable body showing `{"command": "git status"}` formatted as JSON

#### Scenario: Tool result appended to tool call card

- **WHEN** the log viewer receives a `tool_result` event for `execute_command` following a `tool_call` event for the same tool
- **THEN** the result is appended to the existing tool call card with a "Result (342 chars)" section

#### Scenario: Thinking text rendered with muted style

- **WHEN** the log viewer receives a `thinking` event with text "I need to check the git status first"
- **THEN** the viewer displays the text in an italic, muted-colour block

#### Scenario: Reasoning text rendered with accent style

- **WHEN** the log viewer receives a `reasoning` event with text "The user wants to deploy..."
- **THEN** the viewer displays the text in a distinct styled block with a left border accent

#### Scenario: Long thinking text collapsed by default

- **WHEN** the log viewer receives a `thinking` event with text exceeding 3 lines
- **THEN** the text block is collapsed by default with a "Show more" toggle

#### Scenario: Error rendered as alert

- **WHEN** the log viewer receives an `error` event with message "API authentication failed"
- **THEN** the viewer displays a red-styled alert block with the message

#### Scenario: Auto-scroll follows new events

- **WHEN** the user has not manually scrolled and a new event arrives
- **THEN** the log viewer scrolls to show the latest event

#### Scenario: Manual scroll disables auto-scroll

- **WHEN** the user scrolls up in the log viewer and a new event arrives
- **THEN** the log viewer does NOT auto-scroll, preserving the user's scroll position

#### Scenario: Raw stderr line rendered as monospace

- **WHEN** the log viewer receives a `raw` event with line "WARNING: deprecated API usage"
- **THEN** the viewer displays the line in monospace font without special formatting
