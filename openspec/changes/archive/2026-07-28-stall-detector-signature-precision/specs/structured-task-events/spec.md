## MODIFIED Requirements

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

## ADDED Requirements

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
