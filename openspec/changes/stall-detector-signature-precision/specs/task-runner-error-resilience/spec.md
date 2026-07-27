## MODIFIED Requirements

### Requirement: No-progress loop detection (stall guard)

The task runner SHALL detect a no-progress loop within a single agent attempt and
abort it, rather than letting a stuck run consume the full `MAX_TURNS` budget. A
no-progress loop is defined as the same tool being called with byte-identical
arguments **and returning an unchanged result**. Repeating a call whose result
changes is progress, not a stall, and SHALL NOT be treated as a loop.

The runner SHALL maintain, per agent attempt, one counter per tool-call key, where a
key is the tool name combined with its canonicalised arguments (JSON with sorted
keys; a stable fallback when the arguments are not JSON-serializable). Argument key
ordering SHALL NOT affect the key, and distinct tools or distinct arguments SHALL be
counted independently.

Alongside each key's counter the runner SHALL retain a digest of the result returned
by that key's most recent invocation. The digest SHALL be computed over the tool's
complete result, not a truncated rendering of it, so that two distinct long results
sharing a prefix are never treated as equal. When a key is invoked:

- if the new result's digest equals the stored digest, the key's counter SHALL be
  incremented;
- otherwise the counter SHALL be reset to 1 and the stored digest replaced.

Invocations of *other* keys SHALL NOT reset a key's counter, so that a loop which
interleaves two or more repeating calls is still detected.

Because the rule depends on the result, the runner SHALL evaluate the guard once a
tool call's output is known, pairing each call with its own output by call
identifier so that concurrently issued calls are matched correctly. A call that never
yields an output SHALL NOT be counted.

The guard SHALL respond in two tiers.

When a key's counter reaches `STALL_NUDGE_LIMIT` (default 3), the runner SHALL
replace that tool call's result, as seen by the model, with a nudge stating that the
call has repeated with an unchanged result, that its effect is already in place, and
that the agent SHALL call `submit_result` if its work is complete or take a different
approach if not. Execution SHALL continue. The nudge text SHALL be a fixed template
into which only the tool name and repeat count are interpolated; no tool-supplied
content SHALL be echoed into it.

A key SHALL be nudged at most once per agent attempt, and issuing a nudge SHALL NOT
reset or otherwise alter any counter. Counting SHALL therefore be performed on the
tool's own result, before any nudge substitution, so that a nudged-but-still-looping
agent continues to accrue toward the abort.

When a key's counter reaches `STALL_REPEAT_LIMIT` (default 6), the runner SHALL abort
the run as a stall.

Both limits SHALL be operator-configurable via environment variables of the same
name, and an unparseable value SHALL fall back to its default with a logged warning.
`STALL_REPEAT_LIMIT <= 0` SHALL disable the guard entirely, including the nudge tier.
`STALL_NUDGE_LIMIT <= 0` SHALL disable only the nudge tier, leaving the abort intact.
A `STALL_NUDGE_LIMIT` greater than or equal to `STALL_REPEAT_LIMIT` SHALL be treated
as disabling the nudge tier, with a logged warning, rather than silently reordering
the tiers.

A fresh detector SHALL be used for each agent attempt so that a legitimate retry
starts with a clean count and no record of prior nudges.

A stall abort SHALL NOT be retried: the runner SHALL record the task as `failed`
with an error classified as `stalled` and exit non-zero, because the same prompt
and model would reproduce the loop. The offending tool call SHALL remain visible in
the transcript; both its `tool_call` and `tool_result` events precede the abort.

#### Scenario: Identical repeats with unchanged result trip the guard

- **WHEN** an agent attempt calls the same tool with byte-identical arguments
  `STALL_REPEAT_LIMIT` times and each call returns the same result
- **THEN** the run is aborted with a `stalled` error and is not retried

#### Scenario: Nudge fires before the abort and the run continues

- **WHEN** a key's counter reaches `STALL_NUDGE_LIMIT`
- **THEN** the model receives the nudge text in place of that call's result, the run
  continues, and no `stalled` error is raised

#### Scenario: A nudged agent that keeps looping still aborts

- **WHEN** an agent is nudged at `STALL_NUDGE_LIMIT` and continues issuing the same
  call with the same result
- **THEN** the counter keeps accruing on the tool's own result and the run aborts on
  reaching `STALL_REPEAT_LIMIT`

#### Scenario: A key is nudged only once per attempt

- **WHEN** a key has already been nudged in this agent attempt and its counter
  continues to rise
- **THEN** no further nudge is issued for that key, and the model sees the tool's real
  results until the abort

#### Scenario: Nudge tier can be disabled independently

- **WHEN** `STALL_NUDGE_LIMIT` is `0`, negative, or greater than or equal to
  `STALL_REPEAT_LIMIT`
- **THEN** no nudge is ever issued, a warning is logged for the misordered case, and
  the hard abort still trips at `STALL_REPEAT_LIMIT`

#### Scenario: Disabling the guard disables both tiers

- **WHEN** `STALL_REPEAT_LIMIT` is `0` or negative
- **THEN** neither a nudge nor an abort occurs, regardless of how many identical calls
  with identical results are made

#### Scenario: A changing result resets the counter

- **WHEN** an agent calls the same tool with byte-identical arguments repeatedly but
  the tool returns a different result each time (e.g. a character-count script
  reporting 207, then 184, then 174 as a draft is revised)
- **THEN** the counter resets on each differing result and the guard does not trip,
  regardless of how many such calls occur

#### Scenario: A later recurrence of an earlier result does not accumulate

- **WHEN** a key returns result A, then result B, then result A again
- **THEN** the counter is 1 after the second occurrence of A, because the intervening
  differing result reset it

#### Scenario: Interleaved repeating calls are still detected

- **WHEN** an agent alternates between two tool calls, each with fixed arguments and
  each returning an unchanged result, for `STALL_REPEAT_LIMIT` rounds
- **THEN** each key accrues independently and the guard trips, because calls to one
  key do not reset the other

#### Scenario: Varied work does not trip the guard

- **WHEN** an agent calls the same tool with different arguments each time (e.g.
  different file paths or URLs)
- **THEN** each distinct key is counted independently and the guard does not trip

#### Scenario: Argument order is not significant

- **WHEN** the same tool is called with the same argument keys in a different order
  and returns an unchanged result
- **THEN** the calls share one key and count toward the same limit

#### Scenario: Long results differing beyond the truncation point are distinguished

- **WHEN** a tool returns two results that are identical up to the transcript
  truncation length but differ afterwards
- **THEN** their digests differ, the counter resets, and the guard does not trip

#### Scenario: Guard is disable-able

- **WHEN** `STALL_REPEAT_LIMIT` is set to `0` or a negative value
- **THEN** the stall guard never trips, regardless of how many identical calls with
  identical results occur

#### Scenario: Retry starts with a clean budget

- **WHEN** an agent attempt fails for a retryable reason and a new attempt begins
- **THEN** the stall counts and stored result digests from the previous attempt do
  not carry over

#### Scenario: A call without an output is not counted

- **WHEN** a tool call is issued but no corresponding output is produced before the
  attempt ends
- **THEN** that call does not increment any counter and does not affect a stored
  digest
