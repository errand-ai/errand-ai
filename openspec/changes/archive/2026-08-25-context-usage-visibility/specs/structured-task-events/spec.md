## MODIFIED Requirements

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
| `llm_turn_start` | `turn_id` (string), `model` (string) | Model call starting; assigns the turn identifier |
| `llm_turn_end` | `turn_id` (string), `input_tokens` (integer), `output_tokens` (integer), `duration_ms` (integer) | Model call completed, with provider-reported usage |
| `context_pressure` | `input_tokens` (integer), `limit` (integer), `threshold` (number) | Context crossed a pressure threshold |
| `context_snapshot` | `input_tokens` (integer), `message_count` (integer), `top_contributors` (array) | Diagnostic detail on a significant context event |

The `tool_result` event's `output` field SHALL be truncated to a maximum of 500 characters. The `length` field SHALL contain the original untruncated length.

The `context_snapshot` event's `top_contributors` entries SHALL identify contributors by role, tool name and size, and SHALL NOT include message content.

Events SHALL be written directly to stderr rather than through the logging framework, so that delivery does not depend on the configured log level. The task runner runs above `INFO` in production, and diagnostics routed through `logger.info` are discarded.

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

#### Scenario: Turn start and end are paired by turn_id

- **WHEN** a model call starts and later completes
- **THEN** stderr contains an `llm_turn_start` and an `llm_turn_end` line sharing the same `turn_id`

#### Scenario: Events emitted regardless of log level

- **WHEN** the task runner is configured at `WARNING`
- **THEN** structured events are still written to stderr

### Requirement: Valkey message format for structured events

The worker SHALL publish structured events to the per-task Valkey pub/sub channel `task_logs:{task_id}` using the format `{"event": "task_event", "type": "<event_type>", "data": <event_data>}`. The `task_log_end` sentinel SHALL remain as `{"event": "task_log_end"}`.

A designated set of event types SHALL be excluded from publication. An excluded event SHALL NOT be published to the channel and SHALL NOT be written to the replay buffer. Excluded events remain on the task runner's stderr and therefore in the container log, where they are available for later analysis.

The exclusion exists because diagnostic events are large and intended for retrospective analysis rather than live viewing. Publishing them and filtering client-side would still carry the payload across the wire and would displace real entries in the bounded replay buffer.

The exclusion SHALL cover both the publish and the buffer write. These are separate operations, and excluding only the publish would leave the payload in the replay buffer — the thing the exclusion exists to protect.

#### Scenario: Structured event published to Valkey

- **WHEN** the worker reads a stderr line `{"type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}`
- **THEN** the worker publishes `{"event": "task_event", "type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}` to the `task_logs:{task_id}` channel

#### Scenario: Non-JSON stderr lines published as raw events

- **WHEN** the worker reads a stderr line that is not valid JSON (e.g., a Python traceback or library log message)
- **THEN** the worker publishes `{"event": "task_event", "type": "raw", "data": {"line": "<raw stderr line>"}}` to the Valkey channel

#### Scenario: Excluded event type is not published

- **WHEN** the worker reads a well-formed event whose type is in the excluded set
- **THEN** the worker publishes nothing for that line

#### Scenario: Excluded event type is not buffered

- **WHEN** the worker reads a well-formed event whose type is in the excluded set
- **THEN** the replay buffer for that task is unchanged

#### Scenario: Excluded events remain available in the container log

- **WHEN** an excluded event has been emitted during a task
- **THEN** the line is still present in the task runner's container log output

#### Scenario: Non-excluded types are unaffected

- **WHEN** the worker reads a well-formed event whose type is not in the excluded set
- **THEN** the event is published and buffered exactly as before

#### Scenario: End sentinel unchanged

- **WHEN** the task runner container exits
- **THEN** the worker publishes `{"event": "task_log_end"}` to the Valkey channel (same format as before)
