## MODIFIED Requirements

### Requirement: Per-task Valkey pub/sub channel for log streaming

The worker SHALL publish structured task runner events to a per-task Valkey pub/sub channel named `task_logs:{task_id}` during container execution. Each stderr line from the task runner container SHALL be parsed as JSON. If the line is valid JSON with `type` and `data` fields, it SHALL be published as `{"event": "task_event", "type": "<event_type>", "data": <event_data>}`. If the line is not valid JSON, it SHALL be published as `{"event": "task_event", "type": "raw", "data": {"line": "<raw_line>"}}`. When container execution completes (regardless of exit code), the worker SHALL publish a final message `{"event": "task_log_end"}` on the same channel.

#### Scenario: Structured event published during execution

- **WHEN** the worker executes a task with id `abc-123` and the container emits stderr line `{"type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}`
- **THEN** the worker publishes `{"event": "task_event", "type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}` to the Valkey channel `task_logs:abc-123`

#### Scenario: Non-JSON stderr line published as raw event

- **WHEN** the worker reads a stderr line `Traceback (most recent call last):` that is not valid JSON
- **THEN** the worker publishes `{"event": "task_event", "type": "raw", "data": {"line": "Traceback (most recent call last):"}}` to the Valkey channel

#### Scenario: End sentinel published after container exit

- **WHEN** the worker finishes streaming stderr for task `abc-123` (container has exited)
- **THEN** the worker publishes `{"event": "task_log_end"}` to the Valkey channel `task_logs:abc-123`

#### Scenario: End sentinel published on non-zero exit

- **WHEN** the worker executes a task and the container exits with a non-zero exit code
- **THEN** the worker publishes `{"event": "task_log_end"}` to the channel after all stderr lines have been published

#### Scenario: No subscribers has no effect

- **WHEN** the worker publishes events to `task_logs:{task_id}` and no clients are subscribed
- **THEN** the messages are silently discarded by Valkey and the worker is not affected

#### Scenario: Valkey unavailable during event publishing

- **WHEN** the worker attempts to publish an event and the sync Redis connection fails
- **THEN** the worker logs a warning and continues execution without interrupting task processing
