## ADDED Requirements

### Requirement: Per-task log event buffer in Valkey

The backend SHALL maintain a per-task event buffer in Valkey alongside the existing `task_logs:{task_id}` pub/sub channel. The buffer SHALL be a Valkey LIST keyed `task_logs_buffer:{task_id}`. Each time a log event is published to the pub/sub channel, the same event JSON SHALL also be appended (`RPUSH`) to the buffer.

The buffer SHALL be capped at a configurable maximum number of entries (admin setting `task_log_buffer_max_entries`, default 5,000) by trimming on every push (`LTRIM <key> -<max> -1`). The buffer SHALL have an expiry refreshed on each push (admin setting `task_log_buffer_ttl_seconds`, default 86,400) so orphaned buffers self-clean if the task manager crashes before publishing `task_log_end`.

When the task manager publishes `task_log_end` for a task, it SHALL delete the buffer (`DEL task_logs_buffer:{task_id}`) immediately after the publish.

A buffer write failure SHALL NOT block or fail the live publish to the pub/sub channel; failures SHALL be logged at warning level using the same pattern as existing publish-failure logging.

#### Scenario: Buffer is appended on every published event

- **WHEN** the task manager publishes `{"event": "task_event", "type": "tool_call", "data": {...}}` to channel `task_logs:42`
- **THEN** the same JSON string is appended to list `task_logs_buffer:42`

#### Scenario: Buffer is trimmed to the configured cap

- **WHEN** the task manager publishes the (max + 1)-th event for a task
- **THEN** the buffer list contains exactly `task_log_buffer_max_entries` entries, with the oldest entry removed

#### Scenario: Buffer expires after TTL

- **WHEN** an event is appended to a task's buffer
- **THEN** the buffer key is given an expiry of `task_log_buffer_ttl_seconds` seconds (refreshed on each push)

#### Scenario: Buffer is deleted on task_log_end

- **WHEN** the task manager publishes `{"event": "task_log_end"}` for task 42
- **THEN** the key `task_logs_buffer:42` is deleted immediately afterwards

#### Scenario: Buffer write failure does not block live publish

- **WHEN** appending to the buffer raises an exception
- **THEN** the failure is logged at warning level
- **AND** the live publish to the pub/sub channel still completes

### Requirement: SSE endpoint replays buffered events on connect

The SSE endpoint `GET /api/tasks/{task_id}/logs/stream` SHALL, after authenticating the client and confirming the task is in `running` status, replay all buffered events for the task before forwarding live pub/sub messages.

The endpoint SHALL subscribe to the `task_logs:{task_id}` pub/sub channel BEFORE reading the buffer, then read all entries from `task_logs_buffer:{task_id}` (`LRANGE 0 -1`) and emit each as an SSE `data:` message identical in shape to a live message. Only after the replay completes SHALL the endpoint enter the live forwarding loop.

If the buffer is empty or missing (e.g., task only just started), the endpoint SHALL skip the replay step and proceed directly to live forwarding.

The endpoint SHALL NOT deduplicate events that may appear in both the buffer replay and the live stream; clients SHALL tolerate duplicate events at the boundary.

#### Scenario: Connect mid-run replays existing events before live stream

- **WHEN** task 42 is `running` and 17 events have been published to its log channel
- **AND** a client opens an SSE connection to `/api/tasks/42/logs/stream?token=<valid-jwt>`
- **THEN** the client receives 17 `data:` messages (the replay), in publish order, before any new live event is forwarded

#### Scenario: Subscribe before snapshot ordering

- **WHEN** the SSE handler begins handling a connection
- **THEN** it subscribes to the pub/sub channel before issuing `LRANGE` on the buffer

#### Scenario: Empty buffer falls through to live mode

- **WHEN** a client connects to `/api/tasks/42/logs/stream?token=<valid-jwt>` and the buffer for task 42 is empty
- **THEN** no replay messages are sent and the endpoint forwards new live events as they arrive

#### Scenario: Task not running still bypasses replay

- **WHEN** a client connects to the SSE endpoint and the task's status is not `running`
- **THEN** the endpoint emits `event: task_log_end\ndata: {}\n\n` and closes, without consulting the buffer
