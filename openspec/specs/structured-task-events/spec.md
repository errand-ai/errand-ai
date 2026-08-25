## Purpose

Structured JSON event protocol emitted by the task runner on stderr for agent lifecycle tracking.
## Requirements
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

### Requirement: Stall detection event

When the task runner aborts an agent run due to a no-progress loop (see the stall
guard in `task-runner-error-resilience`), it SHALL emit a `stall_detected`
structured event to stderr before failing. The event's `data` SHALL identify the
offending tool (`tool`), the number of consecutive identical-result repeats observed
(`repeat_count`), the configured limit (`limit`), the turn on which it tripped
(`turn_id`), and `result_repeated`, which SHALL be `true` to record that the tool's
result was unchanged across those repeats and not merely its arguments. A
corresponding `error` event with `error_type` `stalled` SHALL also be emitted as the
run fails.

`result_repeated` distinguishes transcripts produced under the result-aware rule from
older transcripts recorded when repeats were counted on arguments alone.

#### Scenario: stall_detected emitted on abort

- **WHEN** the stall guard trips on a repeated tool call whose result did not change
- **THEN** a `stall_detected` event is emitted naming the tool, repeat count, limit,
  and `result_repeated: true`, followed by an `error` event whose `error_type` is
  `stalled`

### Requirement: Stall nudge event

When the stall guard issues a soft nudge instead of aborting (see the two-tier stall
guard in `task-runner-error-resilience`), the task runner SHALL emit a `stall_nudge`
structured event to stderr. The event's `data` SHALL identify the offending tool
(`tool`), the number of identical-result repeats observed (`repeat_count`), the
configured nudge threshold (`limit`), and the turn on which it fired (`turn_id`).

A `stall_nudge` SHALL NOT be accompanied by an `error` event, because the run
continues. A run MAY emit a `stall_nudge` and later a `stall_detected` for the same
tool if the agent keeps looping.

#### Scenario: stall_nudge emitted on a soft intervention

- **WHEN** a key's repeat count reaches the nudge threshold and the runner substitutes
  the nudge message for the tool result
- **THEN** a `stall_nudge` event is emitted naming the tool, repeat count, and
  threshold, and no `error` event is emitted

#### Scenario: Nudge then abort produces both events

- **WHEN** an agent is nudged and continues repeating until the abort threshold
- **THEN** the transcript contains a `stall_nudge` followed later by a
  `stall_detected` and an `error` event with `error_type` `stalled`
