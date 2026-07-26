## ADDED Requirements

### Requirement: No-progress loop detection (stall guard)

The task runner SHALL detect a no-progress loop within a single agent attempt and
abort it, rather than letting a stuck run consume the full `MAX_TURNS` budget. A
no-progress loop is defined as the same tool being called with byte-identical
arguments repeatedly.

The runner SHALL maintain, per agent attempt, a count of tool-call signatures
where a signature is the tool name combined with its canonicalised arguments
(JSON with sorted keys; a stable fallback when the arguments are not
JSON-serializable). Argument key ordering SHALL NOT affect the signature, and
distinct tools or distinct arguments SHALL be counted independently.

When a single signature's count reaches the configured limit
(`STALL_REPEAT_LIMIT`, default 6), the runner SHALL abort the run as a stall. The
limit SHALL be operator-configurable via the `STALL_REPEAT_LIMIT` environment
variable; a value `<= 0` SHALL disable the guard entirely, and an unparseable
value SHALL fall back to the default with a logged warning. A fresh detector
SHALL be used for each agent attempt so that a legitimate retry starts with a
clean count.

A stall abort SHALL NOT be retried: the runner SHALL record the task as `failed`
with an error classified as `stalled` and exit non-zero, because the same prompt
and model would reproduce the loop. The offending tool call SHALL remain visible
in the transcript (the guard is evaluated after the `tool_call` event is emitted).

#### Scenario: Identical repeats trip the guard

- **WHEN** an agent attempt calls the same tool with byte-identical arguments
  `STALL_REPEAT_LIMIT` times
- **THEN** the run is aborted with a `stalled` error and is not retried

#### Scenario: Varied work does not trip the guard

- **WHEN** an agent calls the same tool with different arguments each time (e.g.
  different file paths or URLs)
- **THEN** each distinct signature is counted independently and the guard does not
  trip

#### Scenario: Argument order is not significant

- **WHEN** the same tool is called with the same argument keys in a different order
- **THEN** the calls share one signature and count toward the same limit

#### Scenario: Guard is disable-able

- **WHEN** `STALL_REPEAT_LIMIT` is set to `0` or a negative value
- **THEN** the stall guard never trips, regardless of how many identical calls occur

#### Scenario: Retry starts with a clean budget

- **WHEN** an agent attempt fails for a retryable reason and a new attempt begins
- **THEN** the stall count from the previous attempt does not carry over
