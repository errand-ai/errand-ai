## ADDED Requirements

### Requirement: Stall detection event

When the task runner aborts an agent run due to a no-progress loop (see the stall
guard in `task-runner-error-resilience`), it SHALL emit a `stall_detected`
structured event to stderr before failing. The event's `data` SHALL identify the
offending tool (`tool`), the number of identical repeats observed
(`repeat_count`), the configured limit (`limit`), and the turn on which it tripped
(`turn_id`). A corresponding `error` event with `error_type` `stalled` SHALL also
be emitted as the run fails.

#### Scenario: stall_detected emitted on abort

- **WHEN** the stall guard trips on a repeated identical tool call
- **THEN** a `stall_detected` event is emitted naming the tool, repeat count, and
  limit, followed by an `error` event whose `error_type` is `stalled`
